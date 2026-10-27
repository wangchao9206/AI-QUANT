package com.aiquant.paper.service;

import com.aiquant.paper.api.BookReflectionController.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

@Service
public class BookReflectionService {
    private final JdbcTemplate jdbc;
    private final BookPreviewService previews;
    public BookReflectionService(JdbcTemplate jdbc,BookPreviewService previews) { this.jdbc=jdbc;this.previews=previews; }
    public record Book(UUID id,String slug,String title,String author,long reflectionCount,Instant createdAt) {}
    public record Reflection(UUID id,UUID bookId,String category,String content,Instant createdAt) {}
    private static final RowMapper<Book> BOOK=(rs,n)->new Book(rs.getObject("id",UUID.class),rs.getString("slug"),
        rs.getString("title"),rs.getString("author"),rs.getLong("reflection_count"),rs.getTimestamp("created_at").toInstant());
    private static final RowMapper<Reflection> REFLECTION=(rs,n)->new Reflection(rs.getObject("id",UUID.class),
        rs.getObject("book_id",UUID.class),rs.getString("category"),rs.getString("content"),rs.getTimestamp("created_at").toInstant());
    private static final String BOOK_QUERY="select b.*,(select count(*) from paper_trading.reading_reflection r where r.book_id=b.id) as reflection_count from paper_trading.reading_book b";
    public List<Book> books() {
        return jdbc.query(BOOK_QUERY+" order by (slug='distant-savior') desc nulls last,created_at desc,id desc",BOOK);
    }
    public BookPreviewService.Preview preview(UUID id,boolean refresh) {
        Book selected=book(id);
        return previews.find(selected.title(),selected.author(),refresh);
    }
    private Book book(UUID id) {
        var rows=jdbc.query(BOOK_QUERY+" where b.id=?",BOOK,id);
        if(rows.isEmpty()) throw new IllegalArgumentException("书籍不存在，请刷新书架后重试");
        return rows.get(0);
    }
    public Book create(CreateBookRequest r) {
        String title=r.title().strip(),author=r.author()==null?"":r.author().strip();
        jdbc.update("insert into paper_trading.reading_book(id,client_request_id,title,author) values(?,?,?,?) on conflict(client_request_id) do nothing",
            UUID.randomUUID(),r.clientRequestId(),title,author);
        var saved=jdbc.queryForObject(BOOK_QUERY+" where b.client_request_id=?",BOOK,r.clientRequestId());
        if(!saved.title().equals(title)||!saved.author().equals(author)) throw new IllegalStateException("该保存请求已用于其他书籍，请刷新后重试");
        return saved;
    }
    public Map<String,Object> reflections(UUID id,int page,int size) {
        if(page<1||size<1||size>100)throw new IllegalArgumentException("页码至少1，每页1至100条");
        book(id);
        Long total=jdbc.queryForObject("select count(*) from paper_trading.reading_reflection where book_id=?",Long.class,id);
        var items=jdbc.query("select * from paper_trading.reading_reflection where book_id=? order by created_at desc,id desc limit ? offset ?",
            REFLECTION,id,size,(long)(page-1)*size);
        return Map.of("page",page,"pageSize",size,"total",total,"items",items);
    }
    public Reflection reflect(UUID id,CreateReflectionRequest r) {
        book(id);
        String content=r.content().strip();
        jdbc.update("""
            insert into paper_trading.reading_reflection(id,book_id,client_request_id,category,content)
            values(?,?,?,?,?) on conflict(book_id,client_request_id) do nothing
            """,UUID.randomUUID(),id,r.clientRequestId(),r.category(),content);
        var saved=jdbc.queryForObject("select * from paper_trading.reading_reflection where book_id=? and client_request_id=?",
            REFLECTION,id,r.clientRequestId());
        if(!saved.category().equals(r.category())||!saved.content().equals(content))throw new IllegalStateException("该保存请求已用于其他内容，请刷新后重试");
        return saved;
    }
}
