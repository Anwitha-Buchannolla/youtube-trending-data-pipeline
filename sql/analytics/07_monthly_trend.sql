-- Trending volume and views over time (monthly)
SELECT year, month, month_name,
       count(DISTINCT video_id) AS unique_videos,
       count(*)                 AS trending_appearances,
       round(avg(views))        AS avg_views
FROM vw_trending
GROUP BY year, month, month_name
ORDER BY year, month;
