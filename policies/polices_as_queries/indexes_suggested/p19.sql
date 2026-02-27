/*
Missing Index Details from policy-query.sql
The Query Processor estimates that implementing the following index could improve the query cost by 74.5026%.
*/


USE [TPCH]
GO
CREATE NONCLUSTERED INDEX p19_idx
ON [dbo].[partsupp] ([PS_SuppKey])

DROP INDEX p19_idx ON dbo.partsupp
GO

