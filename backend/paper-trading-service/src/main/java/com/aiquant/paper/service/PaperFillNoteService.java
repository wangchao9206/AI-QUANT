package com.aiquant.paper.service;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PaperFillNoteService {
    private final JdbcTemplate jdbc;
    public PaperFillNoteService(JdbcTemplate jdbc){this.jdbc=jdbc;}
    public record SaveNote(@jakarta.validation.constraints.NotNull @jakarta.validation.constraints.Size(max=6000) String content,
        @jakarta.validation.constraints.Min(0) int version){}
    private void requireFill(UUID session,UUID fill){
        if(jdbc.queryForObject("select count(*) from paper_trading.paper_fill where session_id=? and id=?",Integer.class,session,fill)==0)
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"成交记录不存在");
    }
    public Map<String,Object> get(UUID session,UUID fill,UUID owner){
        requireFill(session,fill);
        var rows=jdbc.queryForList("select content,version,updated_at as \"updatedAt\" from paper_trading.paper_fill_note where session_id=? and fill_id=? and owner_id=?",session,fill,owner);
        return rows.isEmpty()?Map.of("content","","version",0):rows.get(0);
    }
    public Map<String,Object> save(UUID session,UUID fill,UUID owner,SaveNote request){
        requireFill(session,fill);
        int changed;
        if(request.version()==0)changed=jdbc.update("""
            insert into paper_trading.paper_fill_note(session_id,fill_id,owner_id,content,version)
            values(?,?,?,?,1) on conflict do nothing
            """,session,fill,owner,request.content());
        else changed=jdbc.update("""
            update paper_trading.paper_fill_note set content=?,version=version+1,updated_at=now()
            where session_id=? and fill_id=? and owner_id=? and version=?
            """,request.content(),session,fill,owner,request.version());
        if(changed!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"心得已在另一页面更新，请先保留草稿，再重新读取");
        return get(session,fill,owner);
    }
}
