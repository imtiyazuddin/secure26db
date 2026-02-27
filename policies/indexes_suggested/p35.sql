/*
Missing Index Details from 6_p27.sql
The Query Processor estimates that implementing the following index could improve the query cost by 27.6725%.
*/



USE [tpch]
GO
CREATE NONCLUSTERED INDEX p35_idx
ON [dbo].[lineitem] ([L_ShipMode])
INCLUDE ([L_PartKey],[L_SuppKey],[L_Quantity],[L_ExtendedPrice],[L_Discount],[L_Tax],[L_ReturnFlag],[L_LineStatus],[L_ShipDate],[L_CommitDate],[L_ReceiptDate],[L_ShipInstruct],[L_Comment],[skip])
GO

