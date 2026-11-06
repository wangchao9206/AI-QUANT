package com.aiquant.identity;

import org.springframework.boot.autoconfigure.mail.MailProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailProperties.class)
class MailConfiguration {
    // Keep the application usable for bootstrap/admin login when SMTP is not configured.
    @Bean JavaMailSender accountMailSender(MailProperties properties){
        var sender=new JavaMailSenderImpl();sender.setHost(properties.getHost());sender.setPort(properties.getPort());
        sender.setUsername(properties.getUsername());sender.setPassword(properties.getPassword());
        sender.setDefaultEncoding("UTF-8");sender.getJavaMailProperties().putAll(properties.getProperties());return sender;
    }
}
