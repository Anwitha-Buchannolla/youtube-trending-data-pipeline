-- Does publish time (UTC hour) influence reaching the trending list?
SELECT publish_hour,
       count(DISTINCT video_id) AS videos,
       round(avg(views))        AS avg_views
FROM vw_trending
GROUP BY publish_hour
ORDER BY publish_hour;
