package com.aiquant.paper.service;

import com.aiquant.paper.api.BookReflectionController.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import static org.junit.jupiter.api.Assertions.*;

/** Writes ONLY to the explicitly named disposable loopback paper_test database. */
@EnabledIfEnvironmentVariable(named="PAPER_TEST_JDBC_URL",matches="jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/paper_test.*")
class BookReflectionIntegrationTests {
    JdbcTemplate jdbc;BookReflectionService service;
    final UUID seed=UUID.fromString("b00c0001-0000-4000-8000-000000000001");
    @BeforeEach void setup() throws Exception {
        String url=System.getenv("PAPER_TEST_JDBC_URL");
        jdbc=new JdbcTemplate(new DriverManagerDataSource(url+(url.contains("?")?"&":"?")+"currentSchema=paper_trading","paper_test","isolated-test-only"));
        assertEquals("paper_test",jdbc.queryForObject("select current_database()",String.class));
        jdbc.execute("create schema if not exists paper_trading");
        jdbc.execute("drop table if exists paper_trading.reading_reflection");jdbc.execute("drop table if exists paper_trading.reading_book");
        String sql=new String(getClass().getResourceAsStream("/db/migration/V5__book_reflections.sql").readAllBytes(),StandardCharsets.UTF_8);
        for(String statement:sql.split(";"))if(!statement.isBlank())jdbc.execute(statement);
        service=new BookReflectionService(jdbc,org.mockito.Mockito.mock(BookPreviewService.class));
    }
    @Test void createsBooksIdempotentlyAndKeepsEditorialSeedSeparateFromUserNotes() {
        assertEquals("遥远的救世主",service.books().get(0).title());assertEquals(0,service.books().get(0).reflectionCount());
        var request=new CreateBookRequest("new-book-request","  自选书籍  "," 作者 ");
        var one=service.create(request);var two=service.create(request);
        assertEquals(one.id(),two.id());assertEquals("自选书籍",one.title());assertEquals(2,service.books().size());
        assertThrows(IllegalStateException.class,()->service.create(new CreateBookRequest(request.clientRequestId(),"不同的书","作者")));
    }
    @Test void persistsNotesWithRetryProtectionAndDoesNotMixBooksOrPages() {
        var other=service.create(new CreateBookRequest("other-book-request","另一本",null));
        var r=new CreateReflectionRequest("reflection-request","IDEA","  检验自己的判断  ");
        var one=service.reflect(seed,r);assertEquals(one.id(),service.reflect(seed,r).id());
        service.reflect(seed,new CreateReflectionRequest("reflection-second","QUESTION","什么条件会推翻判断？"));
        service.reflect(other.id(),r);
        assertEquals(2L,service.reflections(seed,1,1).get("total"));
        assertEquals(1,((java.util.List<?>)service.reflections(seed,2,1).get("items")).size());
        assertEquals(1L,service.reflections(other.id(),1,10).get("total"));
        assertEquals("检验自己的判断",one.content());
        assertThrows(IllegalStateException.class,()->service.reflect(seed,new CreateReflectionRequest(r.clientRequestId(),"IDEA","修改后的不同记录")));
        assertEquals(2L,service.reflections(seed,1,10).get("total"));
    }
    @Test void rejectsInvalidBoundsAndUnknownBooksWithoutCreatingOrphanNotes() {
        assertThrows(IllegalArgumentException.class,()->service.reflections(seed,0,10));
        assertThrows(IllegalArgumentException.class,()->service.reflections(seed,1,101));
        assertThrows(IllegalArgumentException.class,()->service.reflect(UUID.randomUUID(),new CreateReflectionRequest("orphan-request","IDEA","不能串入其他书")));
        assertEquals(0L,jdbc.queryForObject("select count(*) from paper_trading.reading_reflection",Long.class));
    }
}
