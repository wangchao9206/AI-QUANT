package com.aiquant.tenancy;
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import javax.crypto.Mac;import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;
class TenantIdentityTests {
    String secret="unit-test-internal-secret-at-least-32-characters";ObjectMapper mapper=new ObjectMapper();
    String identity(UUID tenant,long expires)throws Exception{
        String data=Base64.getUrlEncoder().withoutPadding().encodeToString(mapper.writeValueAsBytes(Map.of("tenantId",tenant.toString(),"userId",UUID.randomUUID().toString(),"expiresAt",expires)));
        Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8),"HmacSHA256"));return data+"."+Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
    }
    @Test void signed_identity_is_verified_and_expired_or_forged_context_is_rejected()throws Exception{
        UUID tenant=UUID.randomUUID();String valid=identity(tenant,Instant.now().getEpochSecond()+30);assertEquals(tenant,TenantBoundaryConfiguration.verify(valid,secret,mapper));
        for(String invalid:Arrays.asList(null,"tenant-id",valid+"x",identity(tenant,Instant.now().getEpochSecond()-1),identity(tenant,Instant.now().getEpochSecond()+120)))assertThrows(Exception.class,()->TenantBoundaryConfiguration.verify(invalid,secret,mapper));
        assertThrows(Exception.class,()->TenantBoundaryConfiguration.verify(valid,"different-secret",mapper));
    }
}
