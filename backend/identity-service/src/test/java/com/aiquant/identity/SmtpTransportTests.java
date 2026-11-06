package com.aiquant.identity;
import static org.junit.jupiter.api.Assertions.*;
import java.net.*;import java.io.*;import java.nio.charset.StandardCharsets;import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
class SmtpTransportTests {
 @Test void actually_sends_mail_over_smtp()throws Exception{
  try(var server=new ServerSocket(0,1,InetAddress.getLoopbackAddress())){
   server.setSoTimeout(10000);var captured=new CompletableFuture<String>();
   Thread thread=new Thread(()->{try(var socket=server.accept();var reader=new BufferedReader(new InputStreamReader(socket.getInputStream(),StandardCharsets.UTF_8));var out=new PrintWriter(socket.getOutputStream(),true,StandardCharsets.UTF_8)){
    out.print("220 localhost SMTP test\r\n");out.flush();StringBuilder text=new StringBuilder();boolean data=false;
    for(String line;(line=reader.readLine())!=null;){if(data){if(line.equals(".")){data=false;out.print("250 accepted\r\n");out.flush();captured.complete(text.toString());}else text.append(line).append('\n');}
     else if(line.startsWith("DATA")){data=true;out.print("354 send data\r\n");out.flush();}else if(line.startsWith("QUIT")){out.print("221 bye\r\n");out.flush();break;}else{out.print("250 OK\r\n");out.flush();}}
   }catch(Exception e){captured.completeExceptionally(e);}});thread.setDaemon(true);thread.start();
   var sender=new JavaMailSenderImpl();sender.setHost("127.0.0.1");sender.setPort(server.getLocalPort());sender.setDefaultEncoding("UTF-8");sender.getJavaMailProperties().put("mail.smtp.connectiontimeout","5000");sender.getJavaMailProperties().put("mail.smtp.timeout","5000");
   new AccountMail(sender,"127.0.0.1","accounts@example.test","https://example.test").send("user@example.test","VERIFY",Secrets.token());
   String wire=captured.get(10,TimeUnit.SECONDS);assertTrue(wire.contains("To: user@example.test"));assertTrue(wire.contains("From: accounts@example.test"));assertTrue(wire.contains("Content-Type: text/plain"));thread.join(1000);
  }
 }
}
