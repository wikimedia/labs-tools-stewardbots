ALTER TABLE `logging` DROP COLUMN IF EXISTS `l_project`;
DROP INDEX IF EXISTS `project` ON `logging`;
