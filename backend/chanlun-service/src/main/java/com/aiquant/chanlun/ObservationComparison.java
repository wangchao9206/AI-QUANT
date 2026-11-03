package com.aiquant.chanlun;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;

/** Compare archived observations, never today's final geometry at old dates. */
final class ObservationComparison {
    static final String VERSION="observed-geometry-comparison-v1";
    static final double PRICE_TOLERANCE=1e-8;
    record Source(UUID runId,JsonNode result,List<JsonNode> events) {}
    record Key(String type,int start,int end,String direction) {}
    record Pair(String left,String right,List<JsonNode> leftOnly,List<JsonNode> rightOnly,List<Map<String,Object>> flags,int matched) {
        boolean geometryDifferent(){return !leftOnly.isEmpty()||!rightOnly.isEmpty();}
        boolean flagDifferent(){return !flags.isEmpty();}
        Map<String,Object> summary(){return Map.of("left",left,"right",right,"leftOnly",leftOnly.size(),"rightOnly",rightOnly.size(),"matched",matched,"confirmationDifferences",flags.size());}
        Map<String,Object> witness(){return Map.of("summary",summary(),"leftObjects",leftOnly.stream().limit(8).toList(),"rightObjects",rightOnly.stream().limit(8).toList(),"confirmationObjects",flags.stream().limit(8).toList());}
    }
    private static Key key(JsonNode s){return new Key(s.path("type").asText(),s.path("startIndex").asInt(),s.path("endIndex").asInt(),s.path("direction").asText());}
    static String confirmation(JsonNode s){var flag=s.path("engineConfirmed");return flag.isBoolean()?(flag.asBoolean()?"TRUE":"FALSE"):"UNKNOWN";}
    static boolean sameGeometry(JsonNode a,JsonNode b){
        if(!key(a).equals(key(b)))return false;
        for(String field:List.of("startPrice","endPrice","low","high")){
            var x=a.path(field);var y=b.path(field);boolean missingX=x.isNull()||x.isMissingNode(),missingY=y.isNull()||y.isMissingNode();
            if(missingX&&missingY)continue;
            if(!x.isNumber()||!y.isNumber()||!Double.isFinite(x.asDouble())||!Double.isFinite(y.asDouble())||Math.abs(x.asDouble()-y.asDouble())>PRICE_TOLERANCE)return false;
        }
        return true;
    }
    static Pair pair(String left,String right,List<JsonNode> a,List<JsonNode> b){
        var indexed=new HashMap<Key,List<JsonNode>>();for(var item:b)indexed.computeIfAbsent(key(item),k->new ArrayList<>()).add(item);
        var used=new HashSet<String>();var onlyA=new ArrayList<JsonNode>();var onlyB=new ArrayList<JsonNode>();var flags=new ArrayList<Map<String,Object>>();int matched=0;
        for(var item:a){
            JsonNode found=null;
            for(var other:indexed.getOrDefault(key(item),List.of()))if(!used.contains(other.path("id").asText())&&sameGeometry(item,other)){found=other;break;}
            if(found==null){onlyA.add(item);continue;}
            used.add(found.path("id").asText());matched++;
            if(!confirmation(item).equals(confirmation(found)))flags.add(Map.of("left",item,"right",found,"leftFlag",confirmation(item),"rightFlag",confirmation(found)));
        }
        for(var item:b)if(!used.contains(item.path("id").asText()))onlyB.add(item);
        return new Pair(left,right,onlyA,onlyB,flags,matched);
    }
    static void validateSources(List<Source> sources,String layer,boolean confirmedOnly){
        if(sources.size()<2||sources.size()>4)throw new IllegalArgumentException("请选择两个至四个引擎来源");
        var first=sources.get(0).result();var engines=new HashSet<String>();
        int count=first.path("observedBars").asInt();if(count<1||count>1894||first.path("bars").size()!=count)throw new IllegalArgumentException("冻结日线观察界限无效");
        for(var source:sources){var r=source.result();
            if(!engines.add(r.path("engineId").asText()))throw new IllegalArgumentException("同一对照中每个引擎只能选择一个来源");
            if(!r.path("bars").equals(first.path("bars"))||!r.path("datasetHash").equals(first.path("datasetHash"))||!r.path("priceBasis").equals(first.path("priceBasis"))||!r.path("observedBars").equals(first.path("observedBars")))throw new IllegalArgumentException("对照必须使用完全相同的输入、价格口径与观察界限");
            boolean supported=false;for(var capability:r.path("layers"))if(layer.equals(capability.asText()))supported=true;
            if(!supported)throw new IllegalArgumentException(r.path("engineId").asText()+" 未提供所选图层，请取消该来源或更换图层");
            if(confirmedOnly&&layer.equals("ZONE")&&r.path("engineId").asText().equals("czsc"))throw new IllegalArgumentException("CZSC 中枢未提供确定标记，请使用全部已观察结构");
        }
    }
    private static Map<String,Integer> dates(Source source){
        var dates=new HashMap<String,Integer>();int i=0;for(var b:source.result().path("bars"))if(dates.putIfAbsent(b.path("date").asText(),i++)!=null)throw new IllegalArgumentException("当前对照仅支持交易日期唯一的冻结日线");return dates;
    }
    static Map<String,JsonNode> stateAt(Source source,int index){
        var dates=dates(source);var state=new LinkedHashMap<String,JsonNode>();
        for(var e:source.events()){
            Integer observed=dates.get(e.path("observedDate").asText());if(observed==null)throw new IllegalStateException("Unknown observation date");
            if(observed>index)break;
            if("RETRACTED".equals(e.path("eventType").asText()))state.remove(e.path("id").asText());else state.put(e.path("id").asText(),e);
        }
        return state;
    }
    static List<JsonNode> projected(Map<String,JsonNode> state,String layer,boolean confirmedOnly){
        return state.values().stream().filter(s->layer.equals(s.path("type").asText())&&(!confirmedOnly||"TRUE".equals(confirmation(s))))
            .sorted(Comparator.comparingInt((JsonNode s)->s.path("startIndex").asInt()).thenComparingInt(s->s.path("endIndex").asInt()).thenComparing(s->s.path("id").asText())).toList();
    }
    static List<Pair> pairs(List<Source> sources,List<List<JsonNode>> projections){
        var pairs=new ArrayList<Pair>();for(int i=0;i<sources.size();i++)for(int j=i+1;j<sources.size();j++)pairs.add(pair(sources.get(i).result().path("engineId").asText(),sources.get(j).result().path("engineId").asText(),projections.get(i),projections.get(j)));return pairs;
    }
    static Map<String,Object> witness(int index,String date,List<Pair> pairs){return Map.of("observedIndex",index,"date",date,"pairs",pairs.stream().map(Pair::witness).toList());}
    static Map<String,Object> analyze(List<Source> sources,String layer,String projection,boolean confirmedOnly){
        validateSources(sources,layer,confirmedOnly);
        int count=sources.get(0).result().path("observedBars").asInt();
        var pointers=new int[sources.size()];var states=new ArrayList<Map<String,JsonNode>>();var projections=new ArrayList<List<JsonNode>>();var lookups=new ArrayList<Map<String,Integer>>();
        for(var source:sources){states.add(new LinkedHashMap<>());projections.add(List.of());lookups.add(dates(source));}
        var timeline=new ArrayList<Map<String,Object>>();var spans=new ArrayList<Map<String,Object>>();Map<String,Object> first=null,firstGeometry=null,firstConfirmation=null;int spanStart=-1,differentCount=0;List<Pair> previousPairs=List.of();
        for(int index=0;index<count;index++){
            boolean changed=index==0;
            for(int s=0;s<sources.size();s++){
                var events=sources.get(s).events();boolean layerChanged=false;
                while(pointers[s]<events.size()){
                    var event=events.get(pointers[s]);Integer at=lookups.get(s).get(event.path("observedDate").asText());
                    if(at==null||at<index)throw new IllegalStateException("Invalid observation order");if(at>index)break;pointers[s]++;
                    if(!layer.equals(event.path("type").asText()))continue;layerChanged=true;
                    if("RETRACTED".equals(event.path("eventType").asText()))states.get(s).remove(event.path("id").asText());else states.get(s).put(event.path("id").asText(),event);
                }
                if(layerChanged){projections.set(s,projected(states.get(s),layer,confirmedOnly));changed=true;}
            }
            var ps=changed?pairs(sources,projections):previousPairs;previousPairs=ps;
            boolean geometry=ps.stream().anyMatch(Pair::geometryDifferent),flags=ps.stream().anyMatch(Pair::flagDifferent),different=geometry||("WITH_CONFIRMATION".equals(projection)&&flags);
            String date=sources.get(0).result().path("bars").get(index).path("date").asText();
            if(firstGeometry==null&&geometry)firstGeometry=witness(index,date,ps);
            if(firstConfirmation==null&&flags)firstConfirmation=witness(index,date,ps);
            if(first==null&&different)first=witness(index,date,ps);
            if(different){differentCount++;if(spanStart<0)spanStart=index;}
            else if(spanStart>=0){spans.add(Map.of("startIndex",spanStart,"endIndex",index-1));spanStart=-1;}
            var counts=new LinkedHashMap<String,Integer>();for(int s=0;s<sources.size();s++)counts.put(sources.get(s).result().path("engineId").asText(),projections.get(s).size());
            timeline.add(Map.of("observedIndex",index,"date",date,"geometryDifferent",geometry,"confirmationDifferent",flags,"different",different,"counts",counts));
        }
        if(spanStart>=0)spans.add(Map.of("startIndex",spanStart,"endIndex",count-1));
        var metadata=new ArrayList<Map<String,Object>>();for(var s:sources)metadata.add(Map.of("runId",s.runId(),"engineId",s.result().path("engineId").asText(),"profileHash",s.result().path("profileHash").asText(),"engineVersion",s.result().path("engineVersion").asText()));
        var report=new LinkedHashMap<String,Object>();report.put("version",VERSION);report.put("layer",layer);report.put("projection",projection);report.put("confirmedOnly",confirmedOnly);report.put("priceTolerance",PRICE_TOLERANCE);report.put("sources",metadata);report.put("observedBars",count);report.put("datasetHash",sources.get(0).result().path("datasetHash").asText());report.put("observedAsOfDate",sources.get(0).result().path("observedAsOfDate").asText());report.put("priceBasis",sources.get(0).result().path("priceBasis").asText());report.put("firstDifference",first);report.put("firstGeometryDifference",firstGeometry);report.put("firstConfirmationDifference",firstConfirmation);report.put("differentObservationCount",differentCount);report.put("spans",spans);report.put("timeline",timeline);
        report.put("limitations",List.of("比较观察事件，不将最终结构裁成过去结果。","身份只在本引擎内使用；跨引擎按端点、方向、价格几何一一匹配，不强行关联不同起点。","确定标记保留各引擎原始含义，UNKNOWN 不等于 false；标记分歧仅比较几何匹配的结构。","字段相同或不同都不能直接证明准确率、收益或定义等价。"));return report;
    }
}
