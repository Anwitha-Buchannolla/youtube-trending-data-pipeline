-- Weekday vs weekend trending activity
SELECT day_name, is_weekend,
       count(*)          AS trending_appearances,
       round(avg(views)) AS avg_views
FROM vw_trending
GROUP BY day_name, is_weekend, dayofweek(trending_date)
ORDER BY CASE day_name WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
                       WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END;
