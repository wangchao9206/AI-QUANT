package com.aiquant.identity;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;

final class AccessControl {
    static final Map<String,String> MODULES;
    static final Map<String,String> ROUTES;
    static {
        var m=new LinkedHashMap<String,String>();
        for(String row:List.of("overview:总览","news:消息","leads:线索池","market:市场行情","options:期权研究","chanlun:缠论","workflows:策略工作流","research:自主研究","learn:学习","mentors:大佬解读","personal:个人总结","books:书籍感悟","backtest:回测","paper:模拟交易","system:系统状态")){String[] p=row.split(":");m.put(p[0],p[1]);}MODULES=Collections.unmodifiableMap(m);
        ROUTES=Map.ofEntries(Map.entry("/live","market"),Map.entry("/overview","overview"),Map.entry("/news","news"),Map.entry("/leads","leads"),Map.entry("/market","market"),Map.entry("/options","options"),Map.entry("/chanlun","chanlun"),Map.entry("/strategy","workflows"),Map.entry("/research","research"),Map.entry("/learn","learn"),Map.entry("/mentors","mentors"),Map.entry("/personal","personal"),Map.entry("/books","books"),Map.entry("/backtest","backtest"),Map.entry("/paper","paper"),Map.entry("/system","system"));
    }
    final JdbcTemplate db;final ObjectMapper mapper;
    AccessControl(JdbcTemplate db,ObjectMapper mapper){this.db=db;this.mapper=mapper;}
    static Set<String> all(){var set=new LinkedHashSet<String>();MODULES.keySet().forEach(k->{set.add(k+".read");set.add(k+".write");});return set;}
    static void validate(Collection<String> codes){if(codes==null||!all().containsAll(codes))throw Accounts.fail(HttpStatus.BAD_REQUEST,"权限编码不在系统权限目录中。");}
    Set<String> effective(Accounts.Principal p){
        if(p.platformAdmin()||Set.of("OWNER","ADMIN").contains(p.role())){var base=all();if(p.apiKey()&&p.scope().equals("READ"))base.removeIf(k->k.endsWith(".write"));return base;}
        var assigned=db.queryForList("select r.permissions::text,r.enabled from identity.role_assignment x join identity.access_role r on r.id=x.role_id and r.tenant_id=x.tenant_id where x.tenant_id=? and x.user_id=?",p.tenant(),p.user());
        var result=new LinkedHashSet<String>();
        if(assigned.isEmpty()){MODULES.keySet().forEach(k->{result.add(k+".read");if(!p.role().equals("VIEWER"))result.add(k+".write");});}
        else for(var row:assigned)if(Boolean.TRUE.equals(row.get("enabled"))){try{for(var code:mapper.readTree((String)row.get("permissions")))if(all().contains(code.asText()))result.add(code.asText());}catch(Exception e){throw new IllegalStateException("Invalid stored role definition");}}
        if(p.role().equals("VIEWER")||(p.apiKey()&&p.scope().equals("READ")))result.removeIf(k->k.endsWith(".write"));return result;
    }
    static String resource(String path){
        if(path==null)return null;
        if(path.startsWith("/api/chanlun/"))return "chanlun";
        if(path.startsWith("/api/v1/paper/books"))return "books";
        if(path.startsWith("/api/v1/paper/personal"))return "personal";
        if(path.startsWith("/api/v1/paper/workflows"))return "workflows";
        if(path.startsWith("/api/v1/paper/"))return "paper";
        if(path.startsWith("/api/v1/options/"))return "options";
        if(path.startsWith("/api/v1/market/leads"))return "leads";
        if(path.startsWith("/api/v1/market/"))return "market";
        if(path.startsWith("/api/v1/backtest/"))return "backtest";
        if(path.startsWith("/api/v1/data/"))return "system";
        if(path.startsWith("/api/v1/research/mentors"))return "mentors";
        if(path.startsWith("/api/v1/research/radar/news"))return "news";
        if(path.startsWith("/api/v1/research/radar/market")||path.startsWith("/api/v1/research/radar/overseas"))return "market";
        if(path.startsWith("/api/v1/research/radar/"))return "leads";
        if(path.startsWith("/api/v1/research/")||path.startsWith("/api/v1/predictions/")||path.startsWith("/api/v1/strategies/"))return "research";
        return null;
    }
    void business(Accounts.Principal p,String path,boolean mutation){String resource=resource(path);if(resource==null||!effective(p).contains(resource+(mutation?".write":".read")))throw Accounts.fail(HttpStatus.FORBIDDEN,"当前角色没有该功能的"+(mutation?"操作":"访问")+"权限。");}
    List<Map<String,Object>> navigation(Accounts.Principal p){
        Set<String> permissions=effective(p);var rows=db.queryForList("select id,parent_id as \"parentId\",label,path,permission,sort_order as \"sortOrder\",enabled from identity.menu order by sort_order,id");
        var allowed=new HashSet<Object>();for(var row:rows)if(Boolean.TRUE.equals(row.get("enabled"))&&(row.get("permission").equals("")||permissions.contains(row.get("permission"))))allowed.add(row.get("id"));
        boolean changed;do{changed=allowed.removeIf(id->{var row=rows.stream().filter(r->r.get("id").equals(id)).findFirst().orElseThrow();return row.get("parentId")!=null&&!allowed.contains(row.get("parentId"));});}while(changed);
        return rows.stream().filter(r->allowed.contains(r.get("id"))).toList();
    }
}
