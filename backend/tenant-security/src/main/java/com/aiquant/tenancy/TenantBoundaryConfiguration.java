package com.aiquant.tenancy;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class TenantBoundaryConfiguration {
    @Bean OncePerRequestFilter tenantBoundary(JdbcTemplate jdbc,TransactionTemplate tx,ObjectMapper mapper,
            @Value("${IDENTITY_INTERNAL_SECRET:}") String secret){
        if(secret.length()<32)throw new IllegalArgumentException("IDENTITY_INTERNAL_SECRET must contain at least 32 characters");
        return new OncePerRequestFilter(){
            @Override protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
                if(!req.getRequestURI().startsWith("/api/")){chain.doFilter(req,res);return;}
                UUID tenant;
                try{tenant=verify(req.getHeader("X-Aiquant-Identity"),secret,mapper);}catch(Exception e){res.sendError(401,"Verified tenant identity required");return;}
                try{TenantTransactions.run(jdbc,tx,tenant,()->{
                    try{chain.doFilter(req,res);if(res.getStatus()>=400)throw new Rejected();}
                    catch(IOException|ServletException e){throw new Transport(e);}return null;
                });}catch(Rejected e){/* Roll back writes when a controller returned an error. */}
                catch(Transport e){if(e.getCause() instanceof IOException io)throw io;throw (ServletException)e.getCause();}
            }
        };
    }
    public static UUID verify(String identity,String secret,ObjectMapper mapper)throws Exception{
        if(identity==null||identity.length()>2048)throw new IllegalArgumentException();String[] parts=identity.split("\\.");if(parts.length!=2)throw new IllegalArgumentException();
        Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));
        if(!MessageDigest.isEqual(mac.doFinal(parts[0].getBytes(StandardCharsets.UTF_8)),Base64.getUrlDecoder().decode(parts[1])))throw new IllegalArgumentException();
        var json=mapper.readTree(Base64.getUrlDecoder().decode(parts[0]));long expires=json.path("expiresAt").asLong();long now=Instant.now().getEpochSecond();if(expires<now||expires>now+60)throw new IllegalArgumentException();
        UUID.fromString(json.path("userId").asText());return UUID.fromString(json.path("tenantId").asText());
    }
    private static final class Rejected extends RuntimeException{}
    private static final class Transport extends RuntimeException{Transport(Exception e){super(e);}}
}
