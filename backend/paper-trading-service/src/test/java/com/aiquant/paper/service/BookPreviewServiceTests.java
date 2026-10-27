package com.aiquant.paper.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class BookPreviewServiceTests {
    final ObjectMapper mapper=new ObjectMapper();
    final String reader="https://weread.qq.com/web/reader/24e32400813abbf82g011d29";
    ObjectNode book(ArrayNode rows,String title,String author,String url) {
        return rows.addObject().putObject("bookInfo").put("title",title).put("author",author).put("readerLink",url)
            .put("publisher","测试出版社").put("soldout",0).put("ispub",1).put("type",0).put("format","epub");
    }
    @Test void matchesTheOriginalAndRejectsCompanionBooksCommentariesAndOtherAuthors() {
        var root=mapper.createObjectNode();var rows=root.putArray("books");
        book(rows,"天幕红尘（《遥远的救世主》姊妹篇）","豆豆",reader);
        book(rows,"一本书读懂遥远的救世主","姚远",reader);
        book(rows,"遥远的救世主","其他作者",reader);
        book(rows,"遥远的救世主（《天道》影视原著）","豆豆",reader);
        var results=BookPreviewService.matching(root,"《遥远的救世主》","豆豆 著",Instant.now());
        assertEquals(1,results.size());assertEquals("豆豆",results.get(0).author());assertEquals(reader,results.get(0).readerUrl());
    }
    @Test void rejectsNonPlatformScriptsCredentialsPortsQueriesAndUnpublishedOrAudioResults() {
        for(String url:java.util.List.of("javascript:alert(1)","http://weread.qq.com/web/reader/24e32400813abbf82g011d29",
            "https://weread.qq.com.evil.test/web/reader/24e32400813abbf82g011d29","https://user@weread.qq.com/web/reader/24e32400813abbf82g011d29",
            reader+"?redirect=https://evil.test",reader+"#x","https://weread.qq.com:8443/web/reader/24e32400813abbf82g011d29"))assertFalse(BookPreviewService.safeReaderUrl(url),url);
        assertTrue(BookPreviewService.safeReaderUrl(reader));
        var root=mapper.createObjectNode();var rows=root.putArray("books");
        book(rows,"测试书","作者",reader).put("soldout",1);
        book(rows,"测试书","作者",reader).put("ispub",0);
        book(rows,"测试书","作者",reader).put("format","mp3");
        assertTrue(BookPreviewService.matching(root,"测试书","作者",Instant.now()).isEmpty());
    }
    @Test void cachesPublicMetadataAndDoesNotRepeatSearches() {
        var builder=RestClient.builder();var server=MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo(startsWith("https://weread.qq.com/web/search/global?"))).andRespond(withSuccess("{\"books\":[]}",MediaType.APPLICATION_JSON));
        var service=new BookPreviewService(builder.build());
        assertEquals("NOT_FOUND",service.find("未匹配书籍","作者",false).status());
        assertEquals("NOT_FOUND",service.find("未匹配书籍","作者",false).status());server.verify();
    }
    @Test void keepsTheVerifiedOriginalLinkOnProviderFailureWithoutInventingLinksForOtherBooks() {
        var builder=RestClient.builder();var server=MockRestServiceServer.bindTo(builder).build();
        server.expect(anything()).andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));
        server.expect(anything()).andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));
        var service=new BookPreviewService(builder.build());
        var known=service.find("遥远的救世主","豆豆",false);assertEquals("READY",known.status());assertEquals(reader,known.resources().get(0).readerUrl());
        var unknown=service.find("未核对的新书","作者",false);assertEquals("UNAVAILABLE",unknown.status());assertTrue(unknown.resources().isEmpty());server.verify();
    }
}
