package com.aiquant.identity;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component @Order(Ordered.HIGHEST_PRECEDENCE)
class IdentityHttpBoundary extends OncePerRequestFilter {
    private final Set<String> origins;
    private final Accounts accounts;
    IdentityHttpBoundary(@Value("${identity.allowed-origins}") String origins,Accounts accounts){this.origins=Set.copyOf(Arrays.asList(origins.split(",")));this.accounts=accounts;}
    @Override protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException {
        res.setHeader("Cache-Control","no-store");res.setHeader("Referrer-Policy","no-referrer");
        long start=System.nanoTime();boolean failed=false;
boolean track=req.getRequestURI().startsWith("/api/v1/auth/")&&(!Set.of("GET","HEAD","OPTIONS").contains(req.getMethod())||req.getRequestURI().startsWith("/api/v1/auth/manage/")||req.getRequestURI().startsWith("/api/v1/auth/admin/"));
        if(track)try{var p=accounts.authenticate(Accounts.cookie(req,"aq_session"),null,req.getHeader("X-Tenant-Id"),null,false);req.setAttribute("identity.user",p.user());req.setAttribute("identity.tenant",p.tenant());}catch(Exception ignored){}
        try{
            if(req.getRequestURI().startsWith("/api/v1/auth/")&&!Set.of("GET","HEAD","OPTIONS").contains(req.getMethod())){String origin=req.getHeader("Origin");if(origin!=null&&!origins.contains(origin)){res.sendError(403,"Origin not allowed");return;}}
            chain.doFilter(req,res);
        }catch(IOException|ServletException|RuntimeException e){failed=true;throw e;}
        finally{if(track)try{
            accounts.db.update("insert into identity.operation_log(user_id,tenant_id,method,path,status,duration_ms,trace_id) values(?,?,?,?,?,?,?)",req.getAttribute("identity.user"),req.getAttribute("identity.tenant"),req.getMethod(),req.getRequestURI().substring(0,Math.min(300,req.getRequestURI().length())),failed?500:res.getStatus(),(System.nanoTime()-start)/1000000,req.getHeader("X-Trace-Id")==null?null:req.getHeader("X-Trace-Id").substring(0,Math.min(128,req.getHeader("X-Trace-Id").length())));
        }catch(Exception e){org.slf4j.LoggerFactory.getLogger(getClass()).error("identity_operation_log_failed");}}
    }
}
