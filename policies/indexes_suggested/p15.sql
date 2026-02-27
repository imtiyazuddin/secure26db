/*
Missing Index Details from policy-query.sql
The Query Processor estimates that implementing the following index could improve the query cost by 84.4975%.
*/


USE [TPCH]
GO
CREATE NONCLUSTERED INDEX p15_idx
ON [dbo].[orders] ([O_OrderDate])
INCLUDE ([O_CustKey])
GO

-- DROP INDEX p15_idx ON orders
-- GO

