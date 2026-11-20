-- How quickly do videos hit the trending list after publication, by category?
SELECT category_name,
       round(avg(days_to_trend), 2) AS avg_days_to_trend,
       median(days_to_trend)        AS median_days_to_trend,
       min(days_to_trend)           AS min_days,
       max(days_to_trend)           AS max_days
FROM (
    -- first time each video appeared on the list
    SELECT video_id, category_name, min(days_to_trend) AS days_to_trend
    FROM vw_trending
    GROUP BY video_id, category_name
)
GROUP BY category_name
ORDER BY avg_days_to_trend;
