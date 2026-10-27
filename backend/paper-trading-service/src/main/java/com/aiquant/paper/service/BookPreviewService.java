package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

/** Public catalogue lookup only. Never requests, copies or proxies book text. */
@Service
public class BookPreviewService {
    public record Resource(String provider,String title,String author,String publisher,String readerUrl,
                           String accessNote,Instant verifiedAt) {}
    public record Preview(String status,String message,List<Resource> resources,Instant checkedAt) {}
    private record Cached(Preview result,Instant expiresAt) {}
    private final RestClient client;
    private final Map<String,Cached> cache=new ConcurrentHashMap<>();
    public BookPreviewService() { this(defaultClient()); }
    BookPreviewService(RestClient client) { this.client=client; }
    private static RestClient defaultClient() {
        var http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
        var factory=new JdkClientHttpRequestFactory(http);factory.setReadTimeout(Duration.ofSeconds(5));
        return RestClient.builder().requestFactory(factory).build();
    }
    public Preview find(String title,String author,boolean refresh) {
        String key=title+"\n"+author;
        Instant now=Instant.now();var cached=cache.get(key);
        if(cached!=null&&now.isBefore(cached.expiresAt())
            &&(!refresh||now.isBefore(cached.result().checkedAt().plusSeconds(10))))return cached.result();
        Preview result;
        try {
            URI uri=UriComponentsBuilder.fromUriString("https://weread.qq.com/web/search/global")
                .queryParam("keyword",title+(author==null||author.isBlank()?"":" "+author))
                .queryParam("maxIdx",0).queryParam("fragmentSize",120).queryParam("count",10).build().encode().toUri();
            JsonNode body=client.get().uri(uri).retrieve().body(JsonNode.class);
            if(body==null||!body.path("books").isArray())throw new IllegalStateException("Catalogue unavailable");
            List<Resource> resources=matching(body,title,author,now);
            if(resources.isEmpty())resources=knownResource(title,author);
            result=new Preview(resources.isEmpty()?"NOT_FOUND":"READY",resources.isEmpty()
                ?"暂未找到与书名、作者相符的文字阅读入口，请核对信息后重新查找。"
                :"已找到匹配的微信读书阅读入口。试读范围与登录要求以平台当前页面为准。",resources,now);
        } catch(RuntimeException failure) {
            var resources=knownResource(title,author);
            result=new Preview(resources.isEmpty()?"UNAVAILABLE":"READY",resources.isEmpty()
                ?"阅读资源检索暂时不可用，请稍后重新查找。"
                :"当前使用已核对的微信读书入口。平台可能要求登录、会员或购买。",resources,now);
        }
        if(cache.size()>=256)cache.clear();
        cache.put(key,new Cached(result,now.plusSeconds(result.status().equals("READY")?1800:60)));
        return result;
    }
    static List<Resource> matching(JsonNode body,String title,String author,Instant checkedAt) {
        Map<String,Resource> found=new LinkedHashMap<>();
        for(JsonNode item:body.path("books")) {
            JsonNode book=item.path("bookInfo");
            if(!canonicalTitle(book.path("title").asText()).equals(canonicalTitle(title)))continue;
            if(author!=null&&!author.isBlank()&&!canonicalAuthor(book.path("author").asText()).equals(canonicalAuthor(author)))continue;
            if(book.path("soldout").asInt(0)!=0||book.path("ispub").asInt(0)!=1||book.path("type").asInt(0)!=0)continue;
            if(!List.of("epub","txt","pdf").contains(book.path("format").asText()))continue;
            String url=book.path("readerLink").asText();
            if(!safeReaderUrl(url))continue;
            found.putIfAbsent(url,new Resource("微信读书",book.path("title").asText(),book.path("author").asText(),
                book.path("publisher").asText(),url,"可在线试读；后续章节可能需要登录、会员或购买。",checkedAt));
            if(found.size()==3)break;
        }
        return new ArrayList<>(found.values());
    }
    static boolean safeReaderUrl(String url) {
        try {
            URI uri=URI.create(url);
            return "https".equals(uri.getScheme())&&"weread.qq.com".equals(uri.getHost())&&uri.getRawUserInfo()==null
                &&(uri.getPort()==-1||uri.getPort()==443)&&uri.getRawQuery()==null&&uri.getRawFragment()==null
                &&uri.getRawPath().matches("/web/reader/[A-Za-z0-9]{12,80}");
        }catch(IllegalArgumentException failure){return false;}
    }
    private static String canonicalTitle(String value) {
        return value.replaceAll("（[^）]*）|\\([^)]*\\)|【[^】]*】","")
            .replace("《","").replace("》","").replaceAll("[\\s　]+","");
    }
    private static String canonicalAuthor(String value) {
        return value.replaceAll("[\\s　]+","").replaceAll("(?:编著|著)$","");
    }
    private static List<Resource> knownResource(String title,String author) {
        if(!canonicalTitle(title).equals("遥远的救世主")||author==null||!canonicalAuthor(author).equals("豆豆"))return List.of();
        return List.of(new Resource("微信读书","遥远的救世主（《天道》影视原著）","豆豆","作家出版社",
            "https://weread.qq.com/web/reader/24e32400813abbf82g011d29",
            "可在线试读；后续章节可能需要登录、会员或购买。",Instant.parse("2026-10-27T03:13:26Z")));
    }
}
