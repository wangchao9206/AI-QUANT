import {request,type RecordPage} from './api'
export interface ReadingBook {id:string;slug:string|null;title:string;author:string;reflectionCount:number;createdAt:string}
export type ReflectionCategory='IDEA'|'TRADING'|'QUESTION'
export interface BookReflection {id:string;bookId:string;category:ReflectionCategory;content:string;createdAt:string}
export interface BookDraft {clientRequestId:string;title:string;author:string}
export interface ReflectionDraft {clientRequestId:string;category:ReflectionCategory;content:string}
export interface BookPreviewResource {provider:string;title:string;author:string;publisher:string;readerUrl:string;accessNote:string;verifiedAt:string}
export interface BookPreview {status:'READY'|'NOT_FOUND'|'UNAVAILABLE';message:string;resources:BookPreviewResource[];checkedAt:string}
const base='/api/v1/paper/books'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const booksApi={
  books:()=>request<ReadingBook[]>(base),
  preview:(id:string,refresh=false)=>request<BookPreview>(`${base}/${encodeURIComponent(id)}/preview?refresh=${refresh}`),
  create:(body:BookDraft)=>request<ReadingBook>(base,post(body)),
  reflections:(id:string,page=1)=>request<RecordPage<BookReflection>>(`${base}/${encodeURIComponent(id)}/reflections?page=${page}&pageSize=10`),
  reflect:(id:string,body:ReflectionDraft)=>request<BookReflection>(`${base}/${encodeURIComponent(id)}/reflections`,post(body)),
}
