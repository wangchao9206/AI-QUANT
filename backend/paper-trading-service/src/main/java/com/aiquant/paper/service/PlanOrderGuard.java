package com.aiquant.paper.service;

import com.aiquant.paper.api.PaperRequests.PlaceOrderRequest;
import com.aiquant.paper.client.SimulationDataClient.LiveContext;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Owner RLS remains in force. The session lock serializes reservations; the case share lock serializes revisions. */
final class PlanOrderGuard {
    private static final com.fasterxml.jackson.databind.ObjectMapper JSON=new com.fasterxml.jackson.databind.ObjectMapper()
        .enable(com.fasterxml.jackson.databind.DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
    private final JdbcTemplate db;
    PlanOrderGuard(JdbcTemplate db) { this.db=db; }
    static boolean guarded(Map<String,Object> session) { return Boolean.TRUE.equals(session.get("decision_guarded")); }

    private Map<String,Object> binding(UUID id,boolean lock) {
        var rows=db.queryForList("""
            select p.id,p.version,p.fields,c.version latest_version,c.symbol
            from paper_trading.decision_paper d join paper_trading.decision_plan p on p.id=d.plan_id
            join paper_trading.decision_case c on c.id=p.case_id where d.session_id=?
            """+(lock?" for share of c":""),id);
        return rows.size()==1?rows.get(0):null;
    }

    Map<String,Object> summary(Map<String,Object> session) {
        if(!guarded(session)) return Map.of("enabled",false);
        var p=binding((UUID)session.get("id"),false);
        if(p==null||!marketPermission())return Map.of("enabled",true,"ownerVisible",false,"openingAllowed",false,
            "message","此账户受私人计划约束；仅计划本人可新增开仓和撮合开仓挂单。可按原权限平仓或撤单。");
        JsonNode f=fields(p);
        boolean current=p.get("version").equals(p.get("latest_version")),valid=expiry(f).isAfter(Instant.now());
        return Map.of("enabled",true,"ownerVisible",true,"openingAllowed",current&&valid,
            "planId",p.get("id"),"version",p.get("version"),"side",f.path("side").asText(),
            "lots",f.path("lots").asInt(),"budget",number(f,"budget"),
            "message",!current?"已有新计划版本：本账户停止新增开仓，仍可平仓和撤单。":!valid?"计划已过期：停止新增开仓，仍可平仓和撤单。":"新增开仓与成交均核对计划；持仓和开仓挂单共同占用手数、风险与资金。行情及预算将在提交时重新核验。");
    }

    void placement(Map<String,Object> session,PlaceOrderRequest request,LiveContext live) {
        if(!guarded(session)||!"OPEN".equals(request.offset()))return;
        var p=binding((UUID)session.get("id"),true);
        if(p==null||!marketPermission())throw new ResponseStatusException(HttpStatus.FORBIDDEN,"仅具备行情权限的计划本人可在此账户新增开仓。");
        String reason=common(session,p,live);
        if(reason==null){var pending=pending((UUID)session.get("id"));
            pending.add(new Reservation(null,request.side(),request.orderType(),request.quantity(),request.limitPrice(),request.stopPrice()));
            reason=exposure(session,p,live,pending,null,null,0);
        }
        if(reason!=null)throw new ResponseStatusException(HttpStatus.CONFLICT,"计划约束："+reason);
    }

    /** Non-owner refreshes must neither execute nor reject somebody else's private opening orders. */
    boolean canMatch(Map<String,Object> session) {
        return !guarded(session)||(marketPermission()&&binding((UUID)session.get("id"),false)!=null);
    }

    String matching(Map<String,Object> session,LiveContext live,UUID orderId,BigDecimal fillPrice,int quantity) {
        if(!guarded(session))return null;
        var p=binding((UUID)session.get("id"),true);
        if(p==null||!marketPermission())return "当前身份不能核验私人计划";
        String reason=common(session,p,live);
        return reason!=null?reason:exposure(session,p,live,pending((UUID)session.get("id")),orderId,fillPrice,quantity);
    }

    private boolean marketPermission(){return "true".equals(db.queryForObject("select current_setting('app.market_read',true)",String.class));}

    private String common(Map<String,Object> s,Map<String,Object> p,LiveContext live) {
        JsonNode f=fields(p);
        // Clock is checked after both session and case locks, not before a potentially long wait.
        Instant now=db.queryForObject("select clock_timestamp()",Timestamp.class).toInstant();
        if(!p.get("version").equals(p.get("latest_version")))return "已有新计划版本，请使用新版本关联的账户";
        if(!expiry(f).isAfter(now))return "计划有效期已过";
        if(live==null||!"LIVE".equals(live.marketState())||!"FRESH".equals(live.quote().dataStatus())
            ||!fresh(live.checkedAt(),now)||!fresh(live.quote().dataTimestamp(),now))return "需交易时段内30秒以内的有效行情";
        String symbol=p.get("symbol").toString();
        if(!symbol.equals(s.get("current_contract"))||!symbol.equals(live.contract())||!symbol.equals(live.quote().symbol())||!symbol.equals(live.spec().contract())
            ||!"LIVE".equals(s.get("mode"))||!"MANUAL".equals(s.get("strategy_id"))||Boolean.TRUE.equals(s.get("auto_roll")))return "账户或实际合约与计划不一致";
        var spec=live.spec();
        if(spec.volumeMultiple()!=((Number)s.get("volume_multiple")).intValue()||spec.priceTick().compareTo(dec(s,"price_tick"))!=0
            ||spec.commissionPerLot().compareTo(dec(s,"commission_per_lot"))!=0||spec.marginPerLot().compareTo(dec(s,"margin_per_lot"))!=0)return "合约规格已变化，请重新核验";
        if(number(f,"equity").compareTo(dec(s,"initial_cash"))!=0)return "账户资金与冻结计划不一致";
        BigDecimal tick=spec.priceTick();
        for(String field:List.of("entry","stop","target"))if(number(f,field).remainder(tick).signum()!=0)return "计划价格未对齐最小跳动";
        return inside(f,live.quote().price())?null:"当前行情已触及或越过保护价/目标价";
    }

    private String exposure(Map<String,Object> s,Map<String,Object> p,LiveContext live,List<Reservation> orders,
                            UUID filling,BigDecimal fillPrice,int fillQuantity) {
        UUID id=(UUID)s.get("id");JsonNode f=fields(p);
        boolean buy="LONG".equals(f.path("side").asText());String side=buy?"BUY":"SELL";
        var position=db.queryForMap("select * from paper_trading.paper_position where session_id=?",id);
        int lots=((Number)position.get("lots")).intValue(),direction=((Number)position.get("direction")).intValue();
        if(lots>0&&(direction!=(buy?1:-1)||!p.get("symbol").equals(position.get("contract"))))return "已有持仓方向或合约与计划不一致";
        BigDecimal mult=BigDecimal.valueOf(((Number)s.get("volume_multiple")).longValue()),quote=live.quote().price();
        BigDecimal stopFill=adverse(number(f,"stop"),s,!buy);
        BigDecimal consumed=db.queryForObject("select coalesce(sum(greatest(-realized_pnl,0)),0) from paper_trading.paper_fill where session_id=?",BigDecimal.class,id)
            .add(dec(s,"commission_paid"));
        BigDecimal risk=consumed,margin=margin(quote,s).multiply(BigDecimal.valueOf(lots)),reserveFees=BigDecimal.ZERO;
        if(lots>0)risk=risk.add(loss(dec(position,"average_price"),stopFill,buy,mult,lots)).add(fee(stopFill,lots,s));
        long total=lots;
        for(Reservation o:orders){
            if(!side.equals(o.side()))return "开仓方向必须与计划一致";
            BigDecimal requested="LIMIT".equals(o.type())?o.limit():"STOP".equals(o.type())?o.stop():null;
            if(requested!=null&&(requested.remainder(dec(s,"price_tick")).signum()!=0||!inside(f,requested)))return "委托价格必须对齐最小跳动且位于保护价与目标价之间";
            BigDecimal worst=buy?number(f,"entry").max(quote):number(f,"entry").min(quote);
            if(requested!=null)worst=buy?worst.max(requested):worst.min(requested);
            // Limits never pay adverse slippage; reserving the worse reference remains conservative.
            BigDecimal reserved="LIMIT".equals(o.type())?worst:adverse(worst,s,buy);
            int filled=o.id()!=null&&o.id().equals(filling)?fillQuantity:0;
            if(fillPrice!=null&&filled>0){
                if(!inside(f,fillPrice))return "实际成交价已触及或越过保护价/目标价";
                risk=risk.add(loss(fillPrice,stopFill,buy,mult,filled)).add(fee(fillPrice,filled,s)).add(fee(stopFill,filled,s));
                reserveFees=reserveFees.add(fee(fillPrice,filled,s));margin=margin.add(margin(fillPrice,s).multiply(BigDecimal.valueOf(filled)));
            }
            int remaining=o.quantity()-filled;
            if(remaining>0){
                risk=risk.add(loss(reserved,stopFill,buy,mult,remaining)).add(fee(reserved,remaining,s)).add(fee(stopFill,remaining,s));
                reserveFees=reserveFees.add(fee(reserved,remaining,s));margin=margin.add(margin(reserved,s).multiply(BigDecimal.valueOf(remaining)));
            }
            total+=o.quantity();
        }
        if(total>f.path("lots").asLong())return "持仓与开仓挂单合计超过计划手数";
        if(risk.compareTo(number(f,"budget"))>0)return "已发生亏损、手续费及持仓/挂单保护价情景损失合计超过计划预算";
        BigDecimal equity=dec(s,"cash_balance");
        if(lots>0)equity=equity.add(quote.subtract(dec(position,"average_price")).multiply(mult).multiply(BigDecimal.valueOf((long)direction*lots)));
        if(margin.add(reserveFees).compareTo(equity)>0)return "持仓与开仓挂单合计保证金和开仓费用超过可用资金";
        return null;
    }

    private List<Reservation> pending(UUID id){return new ArrayList<>(db.query("select * from paper_trading.paper_order where session_id=? and offset_type='OPEN' and status in ('PENDING','PARTIAL') order by created_at,id",
        (r,n)->new Reservation(r.getObject("id",UUID.class),r.getString("side"),r.getString("order_type"),r.getInt("remaining_quantity"),r.getBigDecimal("limit_price"),r.getBigDecimal("stop_price")),id));}
    private static boolean fresh(Instant time,Instant now){return time!=null&&!time.isBefore(now.minusSeconds(30))&&!time.isAfter(now.plusSeconds(2));}
    private static Instant expiry(JsonNode f){var value=f.path("validUntil");return value.isNumber()?Instant.ofEpochSecond(value.decimalValue().longValue(),value.decimalValue().remainder(BigDecimal.ONE).movePointRight(9).longValue()):Instant.parse(value.asText());}
    private static boolean inside(JsonNode f,BigDecimal price){return "LONG".equals(f.path("side").asText())?price.compareTo(number(f,"stop"))>0&&price.compareTo(number(f,"target"))<0:price.compareTo(number(f,"target"))>0&&price.compareTo(number(f,"stop"))<0;}
    private static BigDecimal loss(BigDecimal entry,BigDecimal stop,boolean buy,BigDecimal mult,int lots){return (buy?entry.subtract(stop):stop.subtract(entry)).max(BigDecimal.ZERO).multiply(mult).multiply(BigDecimal.valueOf(lots));}
    private static BigDecimal fee(BigDecimal price,int lots,Map<String,Object>s){return dec(s,"commission_per_lot").max(price.multiply(dec(s,"fee_rate")).multiply(new BigDecimal(s.get("volume_multiple").toString()))).multiply(BigDecimal.valueOf(lots)).setScale(2,RoundingMode.HALF_UP);}
    private static BigDecimal margin(BigDecimal price,Map<String,Object>s){return dec(s,"margin_per_lot").max(price.multiply(new BigDecimal(s.get("volume_multiple").toString())).multiply(dec(s,"margin_rate")));}
    private static BigDecimal adverse(BigDecimal price,Map<String,Object>s,boolean buy){BigDecimal tick=dec(s,"price_tick"),raw=buy?price.add(tick.multiply(dec(s,"slippage_ticks"))):price.subtract(tick.multiply(dec(s,"slippage_ticks")));return raw.divide(tick,0,buy?RoundingMode.CEILING:RoundingMode.FLOOR).multiply(tick);}
    private static BigDecimal dec(Map<String,Object> row,String key){return (BigDecimal)row.get(key);}
    private static BigDecimal number(JsonNode f,String key){return f.path(key).decimalValue();}
    private static JsonNode fields(Map<String,Object> p){try{return JSON.readTree(p.get("fields").toString());}catch(java.io.IOException e){throw new IllegalStateException("冻结计划不可读取");}}
    private record Reservation(UUID id,String side,String type,int quantity,BigDecimal limit,BigDecimal stop){}
}
