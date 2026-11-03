insert into reading_book(id,client_request_id,slug,title,author)
values ('b00c0002-0000-4000-8000-000000000002','seed-chanlun-original-v1','chanlun-original','缠论（教你炒股票）','缠中说禅')
on conflict do nothing;
