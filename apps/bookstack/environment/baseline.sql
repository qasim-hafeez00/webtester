-- MySQL dump 10.13  Distrib 8.4.10, for Linux (x86_64)
--
-- Host: localhost    Database: bookstack
-- ------------------------------------------------------
-- Server version	8.4.10

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `activities`
--

DROP TABLE IF EXISTS `activities`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `activities` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `detail` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `ip` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  `loggable_id` int DEFAULT NULL,
  `loggable_type` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `activities_user_id_index` (`user_id`),
  KEY `activities_entity_id_index` (`loggable_id`),
  KEY `activities_key_index` (`type`),
  KEY `activities_created_at_index` (`created_at`),
  KEY `activities_ip_index` (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `activities`
--

LOCK TABLES `activities` WRITE;
/*!40000 ALTER TABLE `activities` DISABLE KEYS */;
/*!40000 ALTER TABLE `activities` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `api_tokens`
--

DROP TABLE IF EXISTS `api_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `api_tokens` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `secret` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int unsigned NOT NULL,
  `expires_at` date NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `api_tokens_token_id_unique` (`token_id`),
  KEY `api_tokens_user_id_index` (`user_id`),
  KEY `api_tokens_expires_at_index` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `api_tokens`
--

LOCK TABLES `api_tokens` WRITE;
/*!40000 ALTER TABLE `api_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `api_tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `attachments`
--

DROP TABLE IF EXISTS `attachments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `attachments` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `path` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `extension` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `uploaded_to` int NOT NULL,
  `external` tinyint(1) NOT NULL,
  `order` int NOT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `attachments_uploaded_to_index` (`uploaded_to`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attachments`
--

LOCK TABLES `attachments` WRITE;
/*!40000 ALTER TABLE `attachments` DISABLE KEYS */;
/*!40000 ALTER TABLE `attachments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `books`
--

DROP TABLE IF EXISTS `books`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `books` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `slug` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `image_id` int DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `owned_by` int unsigned NOT NULL,
  `default_template_id` int DEFAULT NULL,
  `description_html` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_rule_id` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `books_slug_index` (`slug`),
  KEY `books_created_by_index` (`created_by`),
  KEY `books_updated_by_index` (`updated_by`),
  KEY `books_owned_by_index` (`owned_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `books`
--

LOCK TABLES `books` WRITE;
/*!40000 ALTER TABLE `books` DISABLE KEYS */;
/*!40000 ALTER TABLE `books` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bookshelves`
--

DROP TABLE IF EXISTS `bookshelves`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bookshelves` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `slug` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int DEFAULT NULL,
  `updated_by` int DEFAULT NULL,
  `image_id` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `owned_by` int unsigned NOT NULL,
  `description_html` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `bookshelves_slug_index` (`slug`),
  KEY `bookshelves_created_by_index` (`created_by`),
  KEY `bookshelves_updated_by_index` (`updated_by`),
  KEY `bookshelves_owned_by_index` (`owned_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bookshelves`
--

LOCK TABLES `bookshelves` WRITE;
/*!40000 ALTER TABLE `bookshelves` DISABLE KEYS */;
/*!40000 ALTER TABLE `bookshelves` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bookshelves_books`
--

DROP TABLE IF EXISTS `bookshelves_books`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bookshelves_books` (
  `bookshelf_id` int unsigned NOT NULL,
  `book_id` int unsigned NOT NULL,
  `order` int unsigned NOT NULL,
  PRIMARY KEY (`bookshelf_id`,`book_id`),
  KEY `bookshelves_books_book_id_foreign` (`book_id`),
  CONSTRAINT `bookshelves_books_book_id_foreign` FOREIGN KEY (`book_id`) REFERENCES `books` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `bookshelves_books_bookshelf_id_foreign` FOREIGN KEY (`bookshelf_id`) REFERENCES `bookshelves` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bookshelves_books`
--

LOCK TABLES `bookshelves_books` WRITE;
/*!40000 ALTER TABLE `bookshelves_books` DISABLE KEYS */;
/*!40000 ALTER TABLE `bookshelves_books` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cache`
--

DROP TABLE IF EXISTS `cache`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cache` (
  `key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `expiration` int NOT NULL,
  UNIQUE KEY `cache_key_unique` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cache`
--

LOCK TABLES `cache` WRITE;
/*!40000 ALTER TABLE `cache` DISABLE KEYS */;
/*!40000 ALTER TABLE `cache` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chapters`
--

DROP TABLE IF EXISTS `chapters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapters` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `book_id` int NOT NULL,
  `slug` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `priority` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `owned_by` int unsigned NOT NULL,
  `description_html` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `default_template_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `chapters_slug_index` (`slug`),
  KEY `chapters_book_id_index` (`book_id`),
  KEY `chapters_priority_index` (`priority`),
  KEY `chapters_created_by_index` (`created_by`),
  KEY `chapters_updated_by_index` (`updated_by`),
  KEY `chapters_owned_by_index` (`owned_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chapters`
--

LOCK TABLES `chapters` WRITE;
/*!40000 ALTER TABLE `chapters` DISABLE KEYS */;
/*!40000 ALTER TABLE `chapters` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `comments`
--

DROP TABLE IF EXISTS `comments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `comments` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `entity_id` int unsigned NOT NULL,
  `entity_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `text` longtext COLLATE utf8mb4_unicode_ci,
  `html` longtext COLLATE utf8mb4_unicode_ci,
  `parent_id` int unsigned DEFAULT NULL,
  `local_id` int unsigned DEFAULT NULL,
  `created_by` int unsigned NOT NULL,
  `updated_by` int unsigned DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `comments_entity_id_entity_type_index` (`entity_id`,`entity_type`),
  KEY `comments_local_id_index` (`local_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `comments`
--

LOCK TABLES `comments` WRITE;
/*!40000 ALTER TABLE `comments` DISABLE KEYS */;
/*!40000 ALTER TABLE `comments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `deletions`
--

DROP TABLE IF EXISTS `deletions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deletions` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `deleted_by` int NOT NULL,
  `deletable_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `deletable_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `deletions_deleted_by_index` (`deleted_by`),
  KEY `deletions_deletable_type_index` (`deletable_type`),
  KEY `deletions_deletable_id_index` (`deletable_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `deletions`
--

LOCK TABLES `deletions` WRITE;
/*!40000 ALTER TABLE `deletions` DISABLE KEYS */;
/*!40000 ALTER TABLE `deletions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `email_confirmations`
--

DROP TABLE IF EXISTS `email_confirmations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `email_confirmations` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `email_confirmations_user_id_index` (`user_id`),
  KEY `email_confirmations_token_index` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `email_confirmations`
--

LOCK TABLES `email_confirmations` WRITE;
/*!40000 ALTER TABLE `email_confirmations` DISABLE KEYS */;
/*!40000 ALTER TABLE `email_confirmations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `entity_permissions`
--

DROP TABLE IF EXISTS `entity_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `entity_permissions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `entity_id` int unsigned NOT NULL,
  `entity_type` varchar(25) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role_id` int unsigned NOT NULL,
  `view` tinyint(1) NOT NULL DEFAULT '0',
  `create` tinyint(1) NOT NULL DEFAULT '0',
  `update` tinyint(1) NOT NULL DEFAULT '0',
  `delete` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `new_entity_permissions_entity_id_entity_type_index` (`entity_id`,`entity_type`),
  KEY `new_entity_permissions_role_id_index` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `entity_permissions`
--

LOCK TABLES `entity_permissions` WRITE;
/*!40000 ALTER TABLE `entity_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `entity_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `failed_jobs`
--

DROP TABLE IF EXISTS `failed_jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `failed_jobs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `uuid` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `connection` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `queue` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `exception` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `failed_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `failed_jobs_uuid_unique` (`uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `failed_jobs`
--

LOCK TABLES `failed_jobs` WRITE;
/*!40000 ALTER TABLE `failed_jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `failed_jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `favourites`
--

DROP TABLE IF EXISTS `favourites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `favourites` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `favouritable_id` int NOT NULL,
  `favouritable_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `favouritable_index` (`favouritable_id`,`favouritable_type`),
  KEY `favourites_user_id_index` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `favourites`
--

LOCK TABLES `favourites` WRITE;
/*!40000 ALTER TABLE `favourites` DISABLE KEYS */;
/*!40000 ALTER TABLE `favourites` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `images`
--

DROP TABLE IF EXISTS `images`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `images` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `url` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `path` varchar(400) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `uploaded_to` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `images_type_index` (`type`),
  KEY `images_uploaded_to_index` (`uploaded_to`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `images`
--

LOCK TABLES `images` WRITE;
/*!40000 ALTER TABLE `images` DISABLE KEYS */;
/*!40000 ALTER TABLE `images` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `imports`
--

DROP TABLE IF EXISTS `imports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `imports` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `path` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size` int NOT NULL,
  `type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `imports_created_by_index` (`created_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `imports`
--

LOCK TABLES `imports` WRITE;
/*!40000 ALTER TABLE `imports` DISABLE KEYS */;
/*!40000 ALTER TABLE `imports` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `jobs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `queue` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempts` tinyint unsigned NOT NULL,
  `reserved_at` int unsigned DEFAULT NULL,
  `available_at` int unsigned NOT NULL,
  `created_at` int unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `jobs_queue_index` (`queue`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `jobs`
--

LOCK TABLES `jobs` WRITE;
/*!40000 ALTER TABLE `jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `joint_permissions`
--

DROP TABLE IF EXISTS `joint_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `joint_permissions` (
  `role_id` int NOT NULL,
  `entity_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_id` int NOT NULL,
  `status` tinyint unsigned NOT NULL,
  `owner_id` int unsigned DEFAULT NULL,
  PRIMARY KEY (`role_id`,`entity_type`,`entity_id`),
  KEY `joint_permissions_entity_id_entity_type_index` (`entity_id`,`entity_type`),
  KEY `joint_permissions_role_id_index` (`role_id`),
  KEY `joint_permissions_status_index` (`status`),
  KEY `joint_permissions_owner_id_index` (`owner_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `joint_permissions`
--

LOCK TABLES `joint_permissions` WRITE;
/*!40000 ALTER TABLE `joint_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `joint_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mfa_values`
--

DROP TABLE IF EXISTS `mfa_values`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mfa_values` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `method` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `mfa_values_user_id_index` (`user_id`),
  KEY `mfa_values_method_index` (`method`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mfa_values`
--

LOCK TABLES `mfa_values` WRITE;
/*!40000 ALTER TABLE `mfa_values` DISABLE KEYS */;
/*!40000 ALTER TABLE `mfa_values` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `migrations`
--

DROP TABLE IF EXISTS `migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `migrations` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `migration` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch` int NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=91 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `migrations`
--

LOCK TABLES `migrations` WRITE;
/*!40000 ALTER TABLE `migrations` DISABLE KEYS */;
INSERT INTO `migrations` VALUES (1,'2014_10_12_000000_create_users_table',1),(2,'2014_10_12_100000_create_password_resets_table',1),(3,'2015_07_12_114933_create_books_table',1),(4,'2015_07_12_190027_create_pages_table',1),(5,'2015_07_13_172121_create_images_table',1),(6,'2015_07_27_172342_create_chapters_table',1),(7,'2015_08_08_200447_add_users_to_entities',1),(8,'2015_08_09_093534_create_page_revisions_table',1),(9,'2015_08_16_142133_create_activities_table',1),(10,'2015_08_29_105422_add_roles_and_permissions',1),(11,'2015_08_30_125859_create_settings_table',1),(12,'2015_08_31_175240_add_search_indexes',1),(13,'2015_09_04_165821_create_social_accounts_table',1),(14,'2015_09_05_164707_add_email_confirmation_table',1),(15,'2015_11_21_145609_create_views_table',1),(16,'2015_11_26_221857_add_entity_indexes',1),(17,'2015_12_05_145049_fulltext_weighting',1),(18,'2015_12_07_195238_add_image_upload_types',1),(19,'2015_12_09_195748_add_user_avatars',1),(20,'2016_01_11_210908_add_external_auth_to_users',1),(21,'2016_02_25_184030_add_slug_to_revisions',1),(22,'2016_02_27_120329_update_permissions_and_roles',1),(23,'2016_02_28_084200_add_entity_access_controls',1),(24,'2016_03_09_203143_add_page_revision_types',1),(25,'2016_03_13_082138_add_page_drafts',1),(26,'2016_03_25_123157_add_markdown_support',1),(27,'2016_04_09_100730_add_view_permissions_to_roles',1),(28,'2016_04_20_192649_create_joint_permissions_table',1),(29,'2016_05_06_185215_create_tags_table',1),(30,'2016_07_07_181521_add_summary_to_page_revisions',1),(31,'2016_09_29_101449_remove_hidden_roles',1),(32,'2016_10_09_142037_create_attachments_table',1),(33,'2017_01_21_163556_create_cache_table',1),(34,'2017_01_21_163602_create_sessions_table',1),(35,'2017_03_19_091553_create_search_index_table',1),(36,'2017_04_20_185112_add_revision_counts',1),(37,'2017_07_02_152834_update_db_encoding_to_ut8mb4',1),(38,'2017_08_01_130541_create_comments_table',1),(39,'2017_08_29_102650_add_cover_image_display',1),(40,'2018_07_15_173514_add_role_external_auth_id',1),(41,'2018_08_04_115700_create_bookshelves_table',1),(42,'2019_07_07_112515_add_template_support',1),(43,'2019_08_17_140214_add_user_invites_table',1),(44,'2019_12_29_120917_add_api_auth',1),(45,'2020_08_04_111754_drop_joint_permissions_id',1),(46,'2020_08_04_131052_remove_role_name_field',1),(47,'2020_09_19_094251_add_activity_indexes',1),(48,'2020_09_27_210059_add_entity_soft_deletes',1),(49,'2020_09_27_210528_create_deletions_table',1),(50,'2020_11_07_232321_simplify_activities_table',1),(51,'2020_12_30_173528_add_owned_by_field_to_entities',1),(52,'2021_01_30_225441_add_settings_type_column',1),(53,'2021_03_08_215138_add_user_slug',1),(54,'2021_05_15_173110_create_favourites_table',1),(55,'2021_06_30_173111_create_mfa_values_table',1),(56,'2021_07_03_085038_add_mfa_enforced_to_roles_table',1),(57,'2021_08_28_161743_add_export_role_permission',1),(58,'2021_09_26_044614_add_activities_ip_column',1),(59,'2021_11_26_070438_add_index_for_user_ip',1),(60,'2021_12_07_111343_create_webhooks_table',1),(61,'2021_12_13_152024_create_jobs_table',1),(62,'2021_12_13_152120_create_failed_jobs_table',1),(63,'2022_01_03_154041_add_webhooks_timeout_error_columns',1),(64,'2022_04_17_101741_add_editor_change_field_and_permission',1),(65,'2022_04_25_140741_update_polymorphic_types',1),(66,'2022_07_16_170051_drop_joint_permission_type',1),(67,'2022_08_17_092941_create_references_table',1),(68,'2022_09_02_082910_fix_shelf_cover_image_types',1),(69,'2022_10_07_091406_flatten_entity_permissions_table',1),(70,'2022_10_08_104202_drop_entity_restricted_field',1),(71,'2023_01_24_104625_refactor_joint_permissions_storage',1),(72,'2023_01_28_141230_copy_color_settings_for_dark_mode',1),(73,'2023_02_20_093655_increase_attachments_path_length',1),(74,'2023_02_23_200227_add_updated_at_index_to_pages',1),(75,'2023_06_10_071823_remove_guest_user_secondary_roles',1),(76,'2023_06_25_181952_remove_bookshelf_create_entity_permissions',1),(77,'2023_07_25_124945_add_receive_notifications_role_permissions',1),(78,'2023_07_31_104430_create_watches_table',1),(79,'2023_08_21_174248_increase_cache_size',1),(80,'2023_12_02_104541_add_default_template_to_books',1),(81,'2023_12_17_140913_add_description_html_to_entities',1),(82,'2024_01_01_104542_add_default_template_to_chapters',1),(83,'2024_02_04_141358_add_views_updated_index',1),(84,'2024_05_04_154409_rename_activity_relation_columns',1),(85,'2024_09_29_140340_ensure_editor_value_set',1),(86,'2024_10_29_114420_add_import_role_permission',1),(87,'2024_11_02_160700_create_imports_table',1),(88,'2024_11_27_171039_add_instance_id_setting',1),(89,'2025_01_29_180933_create_sort_rules_table',1),(90,'2025_02_05_150842_add_sort_rule_id_to_books',1);
/*!40000 ALTER TABLE `migrations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `page_revisions`
--

DROP TABLE IF EXISTS `page_revisions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `page_revisions` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `page_id` int NOT NULL,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `html` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `text` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `slug` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `book_slug` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'version',
  `markdown` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `revision_number` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `page_revisions_page_id_index` (`page_id`),
  KEY `page_revisions_slug_index` (`slug`),
  KEY `page_revisions_book_slug_index` (`book_slug`),
  KEY `page_revisions_type_index` (`type`),
  KEY `page_revisions_revision_number_index` (`revision_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `page_revisions`
--

LOCK TABLES `page_revisions` WRITE;
/*!40000 ALTER TABLE `page_revisions` DISABLE KEYS */;
/*!40000 ALTER TABLE `page_revisions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pages`
--

DROP TABLE IF EXISTS `pages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pages` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `book_id` int NOT NULL,
  `chapter_id` int NOT NULL,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `slug` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `html` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `text` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `priority` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `created_by` int NOT NULL,
  `updated_by` int NOT NULL,
  `draft` tinyint(1) NOT NULL DEFAULT '0',
  `markdown` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `revision_count` int NOT NULL,
  `template` tinyint(1) NOT NULL DEFAULT '0',
  `deleted_at` timestamp NULL DEFAULT NULL,
  `owned_by` int unsigned NOT NULL,
  `editor` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `pages_slug_index` (`slug`),
  KEY `pages_book_id_index` (`book_id`),
  KEY `pages_chapter_id_index` (`chapter_id`),
  KEY `pages_priority_index` (`priority`),
  KEY `pages_created_by_index` (`created_by`),
  KEY `pages_updated_by_index` (`updated_by`),
  KEY `pages_draft_index` (`draft`),
  KEY `pages_template_index` (`template`),
  KEY `pages_owned_by_index` (`owned_by`),
  KEY `pages_updated_at_index` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pages`
--

LOCK TABLES `pages` WRITE;
/*!40000 ALTER TABLE `pages` DISABLE KEYS */;
/*!40000 ALTER TABLE `pages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `password_resets`
--

DROP TABLE IF EXISTS `password_resets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_resets` (
  `email` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL,
  KEY `password_resets_email_index` (`email`),
  KEY `password_resets_token_index` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `password_resets`
--

LOCK TABLES `password_resets` WRITE;
/*!40000 ALTER TABLE `password_resets` DISABLE KEYS */;
/*!40000 ALTER TABLE `password_resets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `permission_role`
--

DROP TABLE IF EXISTS `permission_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permission_role` (
  `permission_id` int unsigned NOT NULL,
  `role_id` int unsigned NOT NULL,
  PRIMARY KEY (`permission_id`,`role_id`),
  KEY `permission_role_role_id_foreign` (`role_id`),
  CONSTRAINT `permission_role_permission_id_foreign` FOREIGN KEY (`permission_id`) REFERENCES `role_permissions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `permission_role_role_id_foreign` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permission_role`
--

LOCK TABLES `permission_role` WRITE;
/*!40000 ALTER TABLE `permission_role` DISABLE KEYS */;
INSERT INTO `permission_role` VALUES (19,1),(20,1),(21,1),(22,1),(23,1),(24,1),(25,1),(26,1),(27,1),(28,1),(29,1),(30,1),(31,1),(32,1),(33,1),(34,1),(35,1),(36,1),(37,1),(38,1),(39,1),(40,1),(41,1),(42,1),(43,1),(44,1),(45,1),(46,1),(47,1),(48,1),(49,1),(50,1),(51,1),(52,1),(53,1),(54,1),(55,1),(56,1),(57,1),(58,1),(59,1),(60,1),(61,1),(62,1),(63,1),(64,1),(65,1),(66,1),(67,1),(68,1),(69,1),(70,1),(71,1),(72,1),(73,1),(74,1),(75,1),(76,1),(77,1),(78,1),(79,1),(24,2),(25,2),(26,2),(27,2),(28,2),(29,2),(30,2),(31,2),(32,2),(33,2),(34,2),(35,2),(36,2),(37,2),(38,2),(39,2),(40,2),(41,2),(42,2),(43,2),(44,2),(45,2),(46,2),(47,2),(48,2),(49,2),(50,2),(51,2),(52,2),(53,2),(66,2),(67,2),(68,2),(69,2),(70,2),(71,2),(72,2),(73,2),(76,2),(48,3),(49,3),(50,3),(51,3),(52,3),(53,3),(66,3),(67,3),(76,3),(48,4),(49,4),(50,4),(51,4),(52,4),(53,4),(66,4),(67,4),(76,4);
/*!40000 ALTER TABLE `permission_role` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `references`
--

DROP TABLE IF EXISTS `references`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `references` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `from_id` int unsigned NOT NULL,
  `from_type` varchar(25) COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_id` int unsigned NOT NULL,
  `to_type` varchar(25) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `references_from_id_index` (`from_id`),
  KEY `references_from_type_index` (`from_type`),
  KEY `references_to_id_index` (`to_id`),
  KEY `references_to_type_index` (`to_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `references`
--

LOCK TABLES `references` WRITE;
/*!40000 ALTER TABLE `references` DISABLE KEYS */;
/*!40000 ALTER TABLE `references` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_permissions` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `permissions_name_unique` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES (19,'settings-manage','Manage Settings',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(20,'users-manage','Manage Users',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(21,'user-roles-manage','Manage Roles & Permissions',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(22,'restrictions-manage-all','Manage All Entity Permissions',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(23,'restrictions-manage-own','Manage Entity Permissions On Own Content',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(24,'book-create-all','Create All Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(25,'book-create-own','Create Own Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(26,'book-update-all','Update All Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(27,'book-update-own','Update Own Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(28,'book-delete-all','Delete All Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(29,'book-delete-own','Delete Own Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(30,'page-create-all','Create All Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(31,'page-create-own','Create Own Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(32,'page-update-all','Update All Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(33,'page-update-own','Update Own Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(34,'page-delete-all','Delete All Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(35,'page-delete-own','Delete Own Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(36,'chapter-create-all','Create All Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(37,'chapter-create-own','Create Own Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(38,'chapter-update-all','Update All Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(39,'chapter-update-own','Update Own Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(40,'chapter-delete-all','Delete All Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(41,'chapter-delete-own','Delete Own Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(42,'image-create-all','Create All Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(43,'image-create-own','Create Own Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(44,'image-update-all','Update All Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(45,'image-update-own','Update Own Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(46,'image-delete-all','Delete All Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(47,'image-delete-own','Delete Own Images',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(48,'book-view-all','View All Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(49,'book-view-own','View Own Books',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(50,'page-view-all','View All Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(51,'page-view-own','View Own Pages',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(52,'chapter-view-all','View All Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(53,'chapter-view-own','View Own Chapters',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(54,'attachment-create-all','Create All Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(55,'attachment-create-own','Create Own Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(56,'attachment-update-all','Update All Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(57,'attachment-update-own','Update Own Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(58,'attachment-delete-all','Delete All Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(59,'attachment-delete-own','Delete Own Attachments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(60,'comment-create-all','Create All Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(61,'comment-create-own','Create Own Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(62,'comment-update-all','Update All Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(63,'comment-update-own','Update Own Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(64,'comment-delete-all','Delete All Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(65,'comment-delete-own','Delete Own Comments',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(66,'bookshelf-view-all','View All BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(67,'bookshelf-view-own','View Own BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(68,'bookshelf-create-all','Create All BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(69,'bookshelf-create-own','Create Own BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(70,'bookshelf-update-all','Update All BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(71,'bookshelf-update-own','Update Own BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(72,'bookshelf-delete-all','Delete All BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(73,'bookshelf-delete-own','Delete Own BookShelves',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(74,'templates-manage','Manage Page Templates',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25'),(75,'access-api','Access system API',NULL,'2026-09-16 07:57:26','2026-09-16 07:57:26'),(76,'content-export','Export Content',NULL,'2026-09-16 07:57:26','2026-09-16 07:57:26'),(77,'editor-change','Change page editor',NULL,'2026-09-16 07:57:26','2026-09-16 07:57:26'),(78,'receive-notifications','Receive & Manage Notifications',NULL,'2026-09-16 07:57:26','2026-09-16 07:57:26'),(79,'content-import','Import Content',NULL,'2026-09-16 07:57:26','2026-09-16 07:57:26');
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_user`
--

DROP TABLE IF EXISTS `role_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_user` (
  `user_id` int unsigned NOT NULL,
  `role_id` int unsigned NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_user_role_id_foreign` (`role_id`),
  CONSTRAINT `role_user_role_id_foreign` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `role_user_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_user`
--

LOCK TABLES `role_user` WRITE;
/*!40000 ALTER TABLE `role_user` DISABLE KEYS */;
INSERT INTO `role_user` VALUES (1,1),(2,4);
/*!40000 ALTER TABLE `role_user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `display_name` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `system_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `external_auth_id` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `mfa_enforced` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `roles_system_name_index` (`system_name`),
  KEY `roles_external_auth_id_index` (`external_auth_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'Admin','Administrator of the whole application','2026-09-16 07:57:25','2026-09-16 07:57:25','admin','',0),(2,'Editor','User can edit Books, Chapters & Pages','2026-09-16 07:57:25','2026-09-16 07:57:25','','',0),(3,'Viewer','User can view books & their content behind authentication','2026-09-16 07:57:25','2026-09-16 07:57:25','','',0),(4,'Public','The role given to public visitors if allowed','2026-09-16 07:57:25','2026-09-16 07:57:25','public','',0);
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `search_terms`
--

DROP TABLE IF EXISTS `search_terms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `search_terms` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `term` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `entity_id` int NOT NULL,
  `score` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `search_terms_term_index` (`term`),
  KEY `search_terms_entity_type_index` (`entity_type`),
  KEY `search_terms_entity_type_entity_id_index` (`entity_type`,`entity_id`),
  KEY `search_terms_score_index` (`score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `search_terms`
--

LOCK TABLES `search_terms` WRITE;
/*!40000 ALTER TABLE `search_terms` DISABLE KEYS */;
/*!40000 ALTER TABLE `search_terms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sessions`
--

DROP TABLE IF EXISTS `sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sessions` (
  `id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int DEFAULT NULL,
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` text COLLATE utf8mb4_unicode_ci,
  `payload` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_activity` int NOT NULL,
  UNIQUE KEY `sessions_id_unique` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sessions`
--

LOCK TABLES `sessions` WRITE;
/*!40000 ALTER TABLE `sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `settings`
--

DROP TABLE IF EXISTS `settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `settings` (
  `setting_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'string',
  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `settings`
--

LOCK TABLES `settings` WRITE;
/*!40000 ALTER TABLE `settings` DISABLE KEYS */;
INSERT INTO `settings` VALUES ('instance-id','af50356a-3471-4fc7-b99e-1ad0d8f7425e','2026-09-16 07:57:26','2026-09-16 07:57:26','string');
/*!40000 ALTER TABLE `settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `social_accounts`
--

DROP TABLE IF EXISTS `social_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `social_accounts` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `driver` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `driver_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `avatar` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `social_accounts_user_id_index` (`user_id`),
  KEY `social_accounts_driver_index` (`driver`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `social_accounts`
--

LOCK TABLES `social_accounts` WRITE;
/*!40000 ALTER TABLE `social_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `social_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sort_rules`
--

DROP TABLE IF EXISTS `sort_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sort_rules` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sequence` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sort_rules`
--

LOCK TABLES `sort_rules` WRITE;
/*!40000 ALTER TABLE `sort_rules` DISABLE KEYS */;
/*!40000 ALTER TABLE `sort_rules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tags`
--

DROP TABLE IF EXISTS `tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tags` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `entity_id` int NOT NULL,
  `entity_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `order` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `tags_name_index` (`name`),
  KEY `tags_value_index` (`value`),
  KEY `tags_order_index` (`order`),
  KEY `tags_entity_id_entity_type_index` (`entity_id`,`entity_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tags`
--

LOCK TABLES `tags` WRITE;
/*!40000 ALTER TABLE `tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_invites`
--

DROP TABLE IF EXISTS `user_invites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_invites` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `user_invites_user_id_index` (`user_id`),
  KEY `user_invites_token_index` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_invites`
--

LOCK TABLES `user_invites` WRITE;
/*!40000 ALTER TABLE `user_invites` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_invites` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(60) COLLATE utf8mb4_unicode_ci NOT NULL,
  `remember_token` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `email_confirmed` tinyint(1) NOT NULL DEFAULT '1',
  `image_id` int NOT NULL DEFAULT '0',
  `external_auth_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `system_name` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `slug` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `users_email_unique` (`email`),
  UNIQUE KEY `users_slug_unique` (`slug`),
  KEY `users_external_auth_id_index` (`external_auth_id`),
  KEY `users_system_name_index` (`system_name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'Admin','admin@admin.com','$2y$12$gZtPI8CW9vNQpwgoJPlLq.cpMBH5Fe.gutyyftbLt9kWeucsCef1.',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25',1,0,'',NULL,'admin'),(2,'Guest','guest@example.com','',NULL,'2026-09-16 07:57:25','2026-09-16 07:57:25',1,0,'','public','guest');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `views`
--

DROP TABLE IF EXISTS `views`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `views` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `viewable_id` int NOT NULL,
  `viewable_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `views` int NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `views_user_id_index` (`user_id`),
  KEY `views_viewable_id_index` (`viewable_id`),
  KEY `views_updated_at_index` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `views`
--

LOCK TABLES `views` WRITE;
/*!40000 ALTER TABLE `views` DISABLE KEYS */;
/*!40000 ALTER TABLE `views` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `watches`
--

DROP TABLE IF EXISTS `watches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `watches` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `watchable_id` int NOT NULL,
  `watchable_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `level` tinyint unsigned NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `watchable_index` (`watchable_id`,`watchable_type`),
  KEY `watches_user_id_index` (`user_id`),
  KEY `watches_level_index` (`level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `watches`
--

LOCK TABLES `watches` WRITE;
/*!40000 ALTER TABLE `watches` DISABLE KEYS */;
/*!40000 ALTER TABLE `watches` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `webhook_tracked_events`
--

DROP TABLE IF EXISTS `webhook_tracked_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_tracked_events` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `webhook_id` int NOT NULL,
  `event` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `webhook_tracked_events_event_index` (`event`),
  KEY `webhook_tracked_events_webhook_id_index` (`webhook_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_tracked_events`
--

LOCK TABLES `webhook_tracked_events` WRITE;
/*!40000 ALTER TABLE `webhook_tracked_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_tracked_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `webhooks`
--

DROP TABLE IF EXISTS `webhooks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhooks` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL,
  `endpoint` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `timeout` int unsigned NOT NULL DEFAULT '3',
  `last_error` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_called_at` timestamp NULL DEFAULT NULL,
  `last_errored_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `webhooks_name_index` (`name`),
  KEY `webhooks_active_index` (`active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhooks`
--

LOCK TABLES `webhooks` WRITE;
/*!40000 ALTER TABLE `webhooks` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhooks` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-16  7:57:29
