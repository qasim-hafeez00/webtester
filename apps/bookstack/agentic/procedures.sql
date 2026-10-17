-- Snapshot/restore for BookStack (MySQL 8.4), the counterpart of Conduit's agentic_reset().
-- agentic_snapshot(): copy every app table (not sessions, cache, jobs, migrations) into the
--   agentic_snap schema. Taken once, right after BookStack's migrations and before the seed.
-- agentic_restore(): truncate those tables and copy the snapshot back. Sessions are file-based
--   and never touched, so logged-in browser sessions stay valid across resets (needed by the
--   evidence gate, which restores a worker's cookies before replaying).
CREATE DATABASE IF NOT EXISTS agentic_snap;
CREATE DATABASE IF NOT EXISTS agentic_meta;
DROP PROCEDURE IF EXISTS bookstack.agentic_snapshot;
DROP PROCEDURE IF EXISTS bookstack.agentic_restore;

DELIMITER //
CREATE PROCEDURE bookstack.agentic_snapshot()
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE t VARCHAR(128);
  DECLARE cur CURSOR FOR
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'bookstack' AND table_type = 'BASE TABLE'
      AND table_name NOT IN ('sessions', 'cache', 'cache_locks', 'jobs', 'job_batches', 'failed_jobs', 'migrations');
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;
  OPEN cur;
  copy_loop: LOOP
    FETCH cur INTO t;
    IF done THEN LEAVE copy_loop; END IF;
    SET @s = CONCAT('DROP TABLE IF EXISTS agentic_snap.`', t, '`');
    PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    SET @s = CONCAT('CREATE TABLE agentic_snap.`', t, '` LIKE bookstack.`', t, '`');
    PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    SET @s = CONCAT('INSERT INTO agentic_snap.`', t, '` SELECT * FROM bookstack.`', t, '`');
    PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
  END LOOP;
  CLOSE cur;
END //

CREATE PROCEDURE bookstack.agentic_restore()
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE t VARCHAR(128);
  DECLARE cur CURSOR FOR
    SELECT table_name FROM information_schema.tables WHERE table_schema = 'agentic_snap';
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;
  SET FOREIGN_KEY_CHECKS = 0;
  OPEN cur;
  restore_loop: LOOP
    FETCH cur INTO t;
    IF done THEN LEAVE restore_loop; END IF;
    SET @s = CONCAT('TRUNCATE TABLE bookstack.`', t, '`');
    PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
    SET @s = CONCAT('INSERT INTO bookstack.`', t, '` SELECT * FROM agentic_snap.`', t, '`');
    PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
  END LOOP;
  CLOSE cur;
  SET FOREIGN_KEY_CHECKS = 1;
END //
DELIMITER ;
