package com.aiquant.tenancy;
import java.util.UUID;
public final class TenantContext {
    public static final UUID LEGACY=UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final ThreadLocal<UUID> CURRENT=new ThreadLocal<>();
    public static UUID current(){return CURRENT.get();}
    public static UUID currentOrLegacy(){return CURRENT.get()==null?LEGACY:CURRENT.get();}
    static void set(UUID id){if(id==null)CURRENT.remove();else CURRENT.set(id);}
}
