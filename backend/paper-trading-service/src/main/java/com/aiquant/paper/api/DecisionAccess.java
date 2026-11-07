package com.aiquant.paper.api;
import com.aiquant.tenancy.TenantBoundaryConfiguration;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class DecisionAccess {
 private DecisionAccess(){}
 static UUID owner(HttpServletRequest req,JdbcTemplate jdbc,ObjectMapper json,String secret,String extra){
  try{
   String token=req.getHeader("X-Aiquant-Identity");TenantBoundaryConfiguration.verify(token,secret,json);
   var payload=json.readTree(Base64.getUrlDecoder().decode(token.split("\\.")[0]));var permissions=new HashSet<String>();
   for(var permission:payload.path("permissions"))permissions.add(permission.asText());
   if(!permissions.contains("market.read")||!permissions.contains("GET".equals(req.getMethod())?"paper.read":"paper.write")||extra!=null&&(!permissions.contains(extra)||!permissions.contains("research.read")))throw new ResponseStatusException(HttpStatus.FORBIDDEN,"当前身份缺少行情、研究或决策档案权限。");
   UUID owner=UUID.fromString(payload.path("userId").asText());jdbc.queryForObject("select set_config('app.user_id',?,true)",String.class,owner.toString());jdbc.queryForObject("select set_config('app.research_read',?,true)",String.class,Boolean.toString(permissions.contains("research.read")));return owner;
  }catch(ResponseStatusException e){throw e;}catch(Exception e){throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"需要经过网关验证的身份。");}
 }
}
