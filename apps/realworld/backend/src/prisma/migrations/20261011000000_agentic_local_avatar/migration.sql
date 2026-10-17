-- [agentic patch P4] The original default avatar lives on the defunct
-- api.realworld.io host; failed image loads would show up as console errors.
ALTER TABLE "User" ALTER COLUMN "image" SET DEFAULT '/images/smiley-cyrus.jpeg';
