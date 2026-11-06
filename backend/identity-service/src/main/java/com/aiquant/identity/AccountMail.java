package com.aiquant.identity;

import java.net.URI;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Component
class AccountMail {
    private final JavaMailSender sender; private final String host,from,url;
    AccountMail(JavaMailSender sender,@Value("${spring.mail.host:}") String host,@Value("${identity.smtp-from:}") String from,@Value("${identity.public-url}") String url){
        this.sender=sender;this.host=host;this.from=from;this.url=url.replaceAll("/+$","");
        URI uri=URI.create(url);
        if(!Set.of("http","https").contains(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null)throw new IllegalArgumentException("PUBLIC_APP_URL must be an absolute application origin");
    }
    void available(){if(host.isBlank()||from.isBlank())throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 SMTP 发信服务，请联系管理员。");}
    boolean hostIsMissing(){return host.isBlank()||from.isBlank();}
    void send(String email,String purpose,String token){
        available();var message=new SimpleMailMessage();message.setFrom(from);message.setTo(email);
        boolean verify=!purpose.equals("RESET");message.setSubject(verify?"AI-QUANT 邮箱验证":"AI-QUANT 重置密码");
        message.setText((verify?"请打开以下链接验证邮箱，链接 30 分钟内有效。\n":"请打开以下链接设置新密码，链接 30 分钟内有效。\n")+url+"/auth/"+(purpose.equals("EMAIL")?"verify-email":verify?"verify":"reset")+"#token="+token+"\n链接仅可使用一次。若非本人操作，请忽略本邮件。");
        try{sender.send(message);}catch(Exception e){throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"邮件发送失败，请检查 SMTP 配置或稍后重试。");}
    }
}
