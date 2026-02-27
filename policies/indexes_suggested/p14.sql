/*
Missing Index Details from policy-query.sql
The Query Processor estimates that implementing the following index could improve the query cost by 91.4147%.
*/


-- USE [TPCH]
-- GO
-- CREATE NONCLUSTERED INDEX p14_idx
-- ON [dbo].[customer] ([C_NationKey],[C_AcctBal])
-- INCLUDE ([C_Name],[C_Address],[C_Phone],[C_MktSegment],[C_Comment],[skip])
-- GO

DROP INDEX p14_idx ON dbo.customer
GO

