/*
Missing Index Details from 7_p16.sql
The Query Processor estimates that implementing the following index could improve the query cost by 12.2253%.
*/

DROP INDEX p16_idx on orders
GO

USE [tpch]
GO
CREATE NONCLUSTERED INDEX p16_idx
ON [dbo].[orders] ([O_CustKey])

GO
