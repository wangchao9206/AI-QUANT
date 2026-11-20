package com.aiquant.paper.service;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaperAutomationScheduler {
    private final PaperAutomationService store;private final PlanAlertClients clients;private final boolean enabled;
    private final UUID worker=UUID.randomUUID();private final AtomicInteger active=new AtomicInteger();
    private final ScheduledExecutorService dispatcher=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"paper-auto-dispatch");t.setDaemon(true);return t;});
    private final ExecutorService pool=Executors.newFixedThreadPool(4,r->{var t=new Thread(r,"paper-auto-worker");t.setDaemon(true);return t;});
    public PaperAutomationScheduler(PaperAutomationService store,PlanAlertClients clients,@Value("${PAPER_AUTOMATION_ENABLED:true}") boolean enabled){this.store=store;this.clients=clients;this.enabled=enabled;}
    @PostConstruct public void start(){if(enabled)dispatcher.scheduleWithFixedDelay(this::tick,5000,1000,TimeUnit.MILLISECONDS);}
    public void tick(){if(!enabled||pool.isShutdown()||active.get()>=4)return;
        try {for(var job:store.claim(worker,4-active.get())){active.incrementAndGet();pool.submit(()->{
            try {String authorization=clients.authorization((UUID)job.get("owner_id"),(UUID)job.get("tenant_id"));
                var prepared="ALLOWED".equals(authorization)?store.prepare(job):null;
                if("ALLOWED".equals(authorization))authorization=clients.authorization((UUID)job.get("owner_id"),(UUID)job.get("tenant_id"));
                store.complete(job,worker,authorization,prepared);
            }catch(RuntimeException e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("paper_automation_failed type={}",e.getClass().getSimpleName());}
            finally{active.decrementAndGet();}
        });}}catch(RuntimeException e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("paper_automation_claim_failed type={}",e.getClass().getSimpleName());}
    }
    @PreDestroy public void close(){dispatcher.shutdownNow();pool.shutdownNow();}
}
