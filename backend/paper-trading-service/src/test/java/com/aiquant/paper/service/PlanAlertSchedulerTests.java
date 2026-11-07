package com.aiquant.paper.service;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
class PlanAlertSchedulerTests {
 @Test void revoked_permissions_do_not_fetch_market_data_or_skip_owner_aware_completion(){
  var store=mock(PlanAlertStore.class);var clients=mock(PlanAlertClients.class);UUID user=UUID.randomUUID(),tenant=UUID.randomUUID();var job=Map.<String,Object>of("owner_id",user,"tenant_id",tenant,"symbol","RB2701");when(store.claim(any(),anyInt())).thenReturn(List.of(job));when(clients.authorization(user,tenant)).thenReturn("DENIED");var scheduler=new PlanAlertScheduler(store,clients,true);
  try{scheduler.tick();verify(store,timeout(3000)).complete(eq(job),any(),eq("DENIED"),isNull(),any());verify(clients,never()).live(anyString());}finally{scheduler.close();}
 }
 @Test void disabled_dispatcher_never_claims_or_contacts_other_services(){var store=mock(PlanAlertStore.class);var clients=mock(PlanAlertClients.class);var scheduler=new PlanAlertScheduler(store,clients,false);try{scheduler.tick();verifyNoInteractions(store,clients);}finally{scheduler.close();}}
}
