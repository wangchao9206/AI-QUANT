package com.aiquant.market.monitor;

import jakarta.annotation.PreDestroy;
import jakarta.annotation.PostConstruct;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MonitorScheduler {
    private final MonitorStore store;private final MonitorClients clients;private final boolean enabled;
    private final UUID worker=UUID.randomUUID();private final AtomicInteger active=new AtomicInteger();
    private final ExecutorService pool=Executors.newFixedThreadPool(4,r->{var t=new Thread(r,"depth-monitor-worker");t.setDaemon(true);return t;});
    private final ScheduledExecutorService dispatcher=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"depth-monitor-dispatcher");t.setDaemon(true);return t;});
    public MonitorScheduler(MonitorStore store,MonitorClients clients,@Value("${MONITOR_SCHEDULER_ENABLED:true}") boolean enabled){this.store=store;this.clients=clients;this.enabled=enabled;}
    @PostConstruct public void start(){if(enabled)dispatcher.scheduleWithFixedDelay(this::tick,5000,250,TimeUnit.MILLISECONDS);}
    public void tick(){
        if(!enabled||pool.isShutdown()||active.get()>=4)return;
        try{for(var job:store.claim(worker,4-active.get())){active.incrementAndGet();pool.submit(()->{try{run(job);}finally{active.decrementAndGet();}});}}
        catch(RuntimeException e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("monitor_claim_failed type={}",e.getClass().getSimpleName());}
    }
    void run(Map<String,Object> job){
        try{
            Map<String,Object> result;
            if(!clients.authorized((UUID)job.get("created_by"),(UUID)job.get("tenant_id"),(String)job.get("asset_type")))
                result=Map.of("status","FORBIDDEN","message","执行者的账号、租户或监控权限已不可用；恢复授权后重新建立基线。","state",Map.of(),"events",List.of());
            else result=clients.evaluate(Map.of("assetType",job.get("asset_type"),"symbol",job.get("symbol"),"seconds",job.get("seconds"),"parameters",store.object(job.get("parameters"))),store.object(job.get("state")));
            store.complete(job,worker,result);
        }catch(RuntimeException e){
            try{store.complete(job,worker,Map.of("status","ERROR","message","后台检查失败，等待自动重试；本轮没有写入触发。","state",store.object(job.get("state")),"events",List.of()));}
            catch(RuntimeException ignored){org.slf4j.LoggerFactory.getLogger(getClass()).warn("monitor_result_persist_failed");}
        }
    }
    @PreDestroy public void close(){dispatcher.shutdownNow();pool.shutdownNow();}
}
