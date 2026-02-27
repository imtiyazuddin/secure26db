/*
Missing Index Details from 21.sql
The Query Processor estimates that implementing the following index could improve the query cost by 52.7254%.
*/

DROP INDEX q21_p16_19 ON orders 
GO

USE [tpch]
GO
CREATE NONCLUSTERED INDEX q21_p16_19
ON [dbo].[orders] ([O_OrderStatus])

GO

