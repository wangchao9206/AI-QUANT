create table reading_book (
    id uuid primary key,
    client_request_id varchar(128) not null unique,
    slug varchar(80) unique,
    title varchar(120) not null check (length(trim(title)) > 0),
    author varchar(80) not null default '',
    created_at timestamptz not null default now()
);
create table reading_reflection (
    id uuid primary key,
    book_id uuid not null references reading_book(id),
    client_request_id varchar(128) not null,
    category varchar(16) not null check (category in ('IDEA','TRADING','QUESTION')),
    content varchar(6000) not null check (length(trim(content)) > 0),
    created_at timestamptz not null default now(),
    unique (book_id,client_request_id)
);
create index reading_reflection_book_page_idx on reading_reflection(book_id,created_at desc,id desc);
insert into reading_book(id,client_request_id,slug,title,author)
values ('b00c0001-0000-4000-8000-000000000001','seed-distant-savior-v1','distant-savior','遥远的救世主','豆豆');
