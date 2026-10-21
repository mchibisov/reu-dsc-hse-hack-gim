-- VK conversation order disambiguates delayed callback fragments without timing guesses.
ALTER TABLE gim.dialog_questions ADD COLUMN sent_cmid bigint CHECK(sent_cmid>0);
GRANT UPDATE(sent_cmid) ON gim.dialog_questions TO gim_worker,gim_bot;
