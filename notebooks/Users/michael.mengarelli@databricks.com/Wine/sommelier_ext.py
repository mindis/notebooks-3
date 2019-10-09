# Databricks notebook source
# MAGIC %md-sandbox 
# MAGIC # Using Collaborative Filtering to recommend wine
# MAGIC Choosing a wine can be a lot like the game of roulette. There are countless varities and flavor profiles, making selection resemble guesswork for the average wine drinker. Many think that price is an indicator of quality, but that is not always the case. 
# MAGIC 
# MAGIC Besides the grape variety (which there are over ten thousand), environmental factors like the climate and PH of the soil can have significant impact on the profile of the wine.  
# MAGIC 
# MAGIC Many fine restaurants employ **sommeliers** to guide customers in the wine selection process. Sommeliers have extensive knowledge in all of the characteristics that contrinute to a wine's profile. Their role is to make accurate recommendations based on your past experiences. 
# MAGIC 
# MAGIC Similar to an experienced sommelier, we will use machine learning to make predictions based on the experiences and preferences of wine drinkers with a similar profile.
# MAGIC 
# MAGIC Our data set, scraped from [Wine Enthusiast](https://www.winemag.com/) contains the following fields:
# MAGIC <img src="https://s3-us-west-2.amazonaws.com/mikem-docs/img/winesplash.jpeg" style="float:right; height: 250px; margin: 10px; border: 1px solid #ddd; border-radius: 15px 15px 15px 15px; padding: 10px"/>
# MAGIC 
# MAGIC * country 
# MAGIC * description
# MAGIC * designation
# MAGIC * points - number of points Wine Enthusiast rated the wine on a scale of 1-100
# MAGIC * price
# MAGIC * province
# MAGIC * region_1
# MAGIC * taster_name
# MAGIC * title (name)
# MAGIC * variety
# MAGIC * winery
# MAGIC 
# MAGIC <small>This experiment was largely motivated by this [project](https://www.kaggle.com/sudhirnl7/wine-recommender).</small>

# COMMAND ----------

# MAGIC %run ./setup

# COMMAND ----------

# MAGIC %md ### Data Engineering

# COMMAND ----------

df = spark.read.schema(schema).csv("/mnt/mikem/datasets/wine_mag") 
df.where("points == 0").count()

# COMMAND ----------

# Read and drop any with null points
df = spark.read.schema(schema).csv("/mnt/mikem/datasets/wine_mag") \
 .na.drop("all", subset=["points"]) \
 .drop("region_2")

# Add country code data
codes = table("mikem.country_codes").select("alpha-3 code", "country")
ratingsDF = df.join(codes, ['country'], "left_outer").withColumnRenamed("alpha-3 code", "cc") \

ratingsDF.createOrReplaceTempView("wine_ratings")

display(ratingsDF)

# COMMAND ----------

# DBTITLE 1,Count
ratingsDF.count()

# COMMAND ----------

# MAGIC %md ## Exploration

# COMMAND ----------

# DBTITLE 1,Distribution of ratings by country
# MAGIC %sql select cc, count(*) from wine_ratings group by cc 

# COMMAND ----------

# DBTITLE 1,Descriptors
from wordcloud import WordCloud,STOPWORDS
import matplotlib.pyplot as plt

# Get all descriptors and serialize to string
l = list(ratingsDF.select('description').toPandas()['description'])
st = ''.join(str(e.encode('ascii','ignore')) for e in l)

wc = WordCloud(max_words=1000, width=640, height=480, background_color="#001a1a", \
 margin=0, stopwords=STOPWORDS, colormap='gist_stern').generate(st)
 
plt.imshow(wc, interpolation='bilinear')
plt.axis("off")
plt.margins(x=0, y=0)
display(plt.show())

# COMMAND ----------

# DBTITLE 1,Price: Top 95 percentile by variety
# MAGIC %sql 
# MAGIC SELECT
# MAGIC   variety, price
# MAGIC FROM (
# MAGIC   SELECT variety, price, 
# MAGIC     ntile(100) OVER (PARTITION BY price order by price) as percentile
# MAGIC   FROM wine_ratings) tmp
# MAGIC WHERE
# MAGIC   percentile > 95
# MAGIC   and price > 100

# COMMAND ----------

# DBTITLE 1,Price vs Points
# MAGIC %sql select points, price from wine_ratings order by price desc limit 100

# COMMAND ----------

# DBTITLE 1,Correlation?
print(ratingsDF.stat.corr("points","price"))

# COMMAND ----------

# MAGIC %md ## Collaborative Filtering

# COMMAND ----------

# DBTITLE 1,Train 
(train,test) = ratingsDF.randomSplit([0.8, 0.2], seed = 42)
print("Counts: train {} test {}".format(train.cache().count(), test.cache().count()))

userIndexer = StringIndexer(inputCol="taster_name", outputCol="user_id", handleInvalid="skip")
titleIndexer = StringIndexer(inputCol="title", outputCol="item_id", handleInvalid="skip")

als = ALS(maxIter=5, regParam=0.01, userCol="user_id", itemCol="item_id", ratingCol="points", coldStartStrategy="drop", nonnegative=True)

pipeline = Pipeline()
pipeline.setStages([userIndexer, titleIndexer, als])

model = pipeline.fit(train)

# COMMAND ----------

# DBTITLE 0,Predict
predictions = model.transform(test)

display(predictions)

# COMMAND ----------

# MAGIC %md ## Recommendations

# COMMAND ----------

display(predictions.filter("user_id == 12"))

# COMMAND ----------

alsModel = model.stages[2]
userRecs = alsModel.recommendForAllUsers(10)
itemRecs = alsModel.recommendForAllItems(10)

# COMMAND ----------

# DBTITLE 1,User recommendations
df = userRecs.filter("user_id == 12").selectExpr("explode(recommendations.item_id) as recommendation")
display(df)

# COMMAND ----------

# MAGIC %md ###Evaluation
# MAGIC We evaluate the recommendation by measuring the Mean Squared Error of rating prediction.

# COMMAND ----------

from pyspark.ml.evaluation import RegressionEvaluator

evaluator = RegressionEvaluator(metricName="rmse", labelCol="points", predictionCol="prediction")
rmse = evaluator.evaluate(predictions)
print("Root-mean-square error = %f" % rmse)

# COMMAND ----------

# MAGIC %md #### Ranking Metrics
# MAGIC Ranking metrics allow us to compare our recommendations with an actual set of ratings for a given user

# COMMAND ----------

perUserActuals = predictions.groupBy("user_id").agg(expr("collect_set(title) as wines"))
display(perUserActuals)

# COMMAND ----------

perUserPredictions = predictions.orderBy(col("user_id"), expr("prediction desc")).groupBy("user_id").agg(expr("collect_list(title) as wines"))
display(perUserPredictions)

# COMMAND ----------

# MAGIC %md #### Recommend for subset

# COMMAND ----------

userIndexer = model.stages[0]
userSubset = userIndexer.transform(ratingsDF).select(als.getUserCol()).distinct().limit(3)

itemIndexer = model.stages[1]
movieSubset = itemIndexer.transform(ratingsDF).select(als.getItemCol()).distinct().limit(3)

# COMMAND ----------

userSubsetRecs = alsModel.recommendForUserSubset(userSubset, 10)
itemSubsetRecs = alsModel.recommendForItemSubset(movieSubset, 10)

# COMMAND ----------

display(userSubsetRecs)

# COMMAND ----------

display(itemSubsetRecs)