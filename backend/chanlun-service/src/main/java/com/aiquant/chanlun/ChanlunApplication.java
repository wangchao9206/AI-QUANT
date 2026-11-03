package com.aiquant.chanlun;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class ChanlunApplication {
    public static void main(String[] args) { SpringApplication.run(ChanlunApplication.class,args); }
}
