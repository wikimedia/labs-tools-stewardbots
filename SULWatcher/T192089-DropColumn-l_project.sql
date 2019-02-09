-- T192089: Drop l_project column at logging table

ALTER TABLE `logging` DROP COLUMN IF EXISTS `l_project`;
DROP INDEX IF EXISTS `project` ON `logging`;
