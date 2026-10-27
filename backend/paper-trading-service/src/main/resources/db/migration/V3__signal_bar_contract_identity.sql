-- Preserve delivery identity so roll basis jumps are not measured as ATR risk.
alter table paper_signal_bar add column contract varchar(16);
