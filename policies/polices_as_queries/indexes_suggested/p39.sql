/*
Missing Index Details from policy-query.sql
The Query Processor estimates that implementing the following index could improve the query cost by 69.3843%.
*/


USE [TPCH]
GO
CREATE NONCLUSTERED INDEX p39_idx
ON [dbo].[lineitem] ([L_ShipMode])
INCLUDE ([L_SuppKey])
GO

DROP INDEX p39_idx ON dbo.lineitem
GO

