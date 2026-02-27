/*
Missing Index Details from 5_p40.sql
The Query Processor estimates that implementing the following index could improve the query cost by 27.551%.
*/

USE [tpch]
GO
CREATE NONCLUSTERED INDEX p40_idx
ON [dbo].[lineitem] ([L_SuppKey])
INCLUDE ([L_PartKey],[L_Quantity],[L_ExtendedPrice],[L_Discount],[L_Tax],[L_ReturnFlag],[L_LineStatus],[L_ShipDate],[L_CommitDate],[L_ReceiptDate],[L_ShipInstruct],[L_ShipMode],[L_Comment],[skip])
GO

