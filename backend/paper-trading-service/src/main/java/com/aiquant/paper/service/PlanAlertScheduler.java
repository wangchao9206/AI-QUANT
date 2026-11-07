package com.aiquant.paper.service;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PlanAlertScheduler {
 private final PlanAlertStore store;private final PlanAlertClients clients;private final boolean enabled;
 private final UUID worker=UUID.randomUUID();private final AtomicInteger active=new AtomicInteger();
 private final ScheduledExecutorService dispatcher=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"plan-alert-dispatch");t.setDaemon(true);return t;});
 private final ExecutorService pool=Executors.newFixedThreadPool(4,r->{var t=new Thread(r,"plan-alert-worker");t.setDaemon(true);return t;});
 public PlanAlertScheduler(PlanAlertStore store,PlanAlertClients clients,@Value("${PLAN_ALERT_SCHEDULER_ENABLED:true}") boolean enabled){this.store=store;this.clients=clients;this.enabled=enabled;}
 @PostConstruct public void start(){if(enabled)dispatcher.scheduleWithFixedDelay(this::tick,5000,1000,TimeUnit.MILLISECONDS);}
 public void tick(){if(!enabled||pool.isShutdown()||active.get()>=4)return;try{for(var job:store.claim(worker,4-active.get())){active.incrementAndGet();pool.submit(()->{try{
   String allowed=clients.authorization((UUID)job.get("owner_id"),(UUID)job.get("tenant_id"));
   store.complete(job,worker,allowed,"ALLOWED".equals(allowed)?clients.live(job.get("symbol").toString()):null,Instant.now());
  }catch(RuntimeException e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("plan_alert_check_failed type={}",e.getClass().getSimpleName());}finally{active.decrementAndGet();}});}}
  catch(RuntimeException e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("plan_alert_claim_failed type={}",e.getClass().getSimpleName());}}
 @PreDestroy public void close(){dispatcher.shutdownNow();pool.shutdownNow();}
}
