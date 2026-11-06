package com.aiquant.paper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@org.springframework.context.annotation.Import(com.aiquant.tenancy.TenantBoundaryConfiguration.class)
public class PaperTradingApplication {
    public static void main(String[] args) {
        SpringApplication.run(PaperTradingApplication.class, args);
    }
}
