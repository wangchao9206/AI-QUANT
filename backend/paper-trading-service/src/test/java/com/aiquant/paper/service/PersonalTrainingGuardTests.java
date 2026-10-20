package com.aiquant.paper.service;
import com.aiquant.paper.api.PaperRequests.*;
import com.aiquant.paper.client.SimulationDataClient;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
class PersonalTrainingGuardTests {
    @Test void genericPaperEndpointsCannotBypassManagedTrainingOrEraseItsJournal() {
        var jdbc=mock(JdbcTemplate.class);var id=UUID.randomUUID();
        when(jdbc.queryForObject(contains("personal_training"),eq(Integer.class),eq(id))).thenReturn(1);
        var service=new PaperTradingService(jdbc,mock(TransactionTemplate.class),mock(SimulationDataClient.class),new MatchingEngine());
        assertThrows(IllegalStateException.class,()->service.advance(id,new AdvanceRequest(10)));
        assertThrows(IllegalStateException.class,()->service.placeOrder(id,new PlaceOrderRequest("unsafe-test","BUY","OPEN","MARKET",10,null,null)));
        assertThrows(IllegalStateException.class,()->service.cancelOrder(id,UUID.randomUUID()));
        assertThrows(IllegalStateException.class,()->service.deleteSession(id));
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
}
