/*
Missing Index Details from policy-query.sql
The Query Processor estimates that implementing the following index could improve the query cost by 56.8077%.
*/


USE [TPCH]
GO
-- CREATE NONCLUSTERED INDEX p12_idx
-- ON [dbo].[lineitem] ([L_Discount])
-- INCLUDE ([L_SuppKey],[L_ExtendedPrice])
-- GO

DROP INDEX p12_idx ON dbo.lineitem
GO

