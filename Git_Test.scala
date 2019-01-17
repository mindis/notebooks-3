// Databricks notebook source
val df = spark.read.option("header", "true")
  .option("delimiter", "\t")
  .option("inferSchema", "true") 
  .csv("/mnt/mikem/mortgage_data")  

display(df)

// COMMAND ----------

display(df.select("unpaid_balance").limit(50))

// COMMAND ----------

import org.apache.spark.sql.functions._
display(df.groupBy("year").agg(avg($"unpaid_balance")))
