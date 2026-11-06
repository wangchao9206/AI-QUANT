package com.aiquant.tenancy;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
public final class TenantTransactions {
    private TenantTransactions(){}
    public static <T>T run(JdbcTemplate jdbc,TransactionTemplate tx,UUID tenant,Supplier<T> work){
        UUID previous=TenantContext.current();
        try {TenantContext.set(tenant);return tx.execute(status->{
            jdbc.execute("set local role aiquant_tenant");
            jdbc.queryForObject("select set_config('app.tenant_id',?,true)",String.class,tenant.toString());
            return work.get();
        });}finally{TenantContext.set(previous);}
    }
}
