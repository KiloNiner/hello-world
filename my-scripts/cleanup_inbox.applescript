-- #!/usr/bin/osascript
-- cleanup_inbox.applescript
-- Moves newsletter/commercial emails from iCloud INBOX and Exchange Indbakke
-- to their respective Deleted folders.
-- Target senders are read from cleanup_senders.txt in the same directory.

-- Load sender list from cleanup_senders.txt (same directory as this script)
set scriptDir to do shell script "dirname " & quoted form of POSIX path of (path to me)
set senderFilePath to scriptDir & "/cleanup_senders.txt"
set rawLines to paragraphs of (do shell script "cat " & quoted form of senderFilePath)

set targetSenders to {}
repeat with ln in rawLines
	set trimmed to ln as string
	if trimmed is not "" and trimmed does not start with "#" then
		set end of targetSenders to trimmed
	end if
end repeat

set movedCount to 0
set skippedCount to 0

log "=== Inbox Cleanup Started ==="
log "Targeting " & (count of targetSenders) & " sender addresses"

tell application "Mail"
	set inbox1 to mailbox "INBOX" of account "iCloud"
	set trash1 to mailbox "Deleted Messages" of account "iCloud"
	set inbox2 to mailbox "Indbakke" of account "Exchange"
	set trash2 to mailbox "Slettet post" of account "Exchange"

	-- iCloud INBOX
	log "--- Processing iCloud INBOX ---"
	set msgs1 to (messages of inbox1 whose deleted status is false)
	set total1 to count of msgs1
	log "Found " & total1 & " messages in iCloud INBOX"
	set toMove1 to {}
	set idx to 0
	repeat with msg in msgs1
		set idx to idx + 1
		log "  Scanning [iCloud] " & idx & "/" & total1
		set sndr to sender of msg
		set matched to false
		repeat with target in targetSenders
			if sndr contains target then
				log "    -> Queuing: " & sndr & " | " & subject of msg
				set end of toMove1 to msg
				set matched to true
				exit repeat
			end if
		end repeat
		if not matched then
			set skippedCount to skippedCount + 1
		end if
	end repeat
	set moveTotal1 to count of toMove1
	log "Deleting " & moveTotal1 & " matched messages from iCloud INBOX"
	set idx to 0
	repeat with msg in toMove1
		set idx to idx + 1
		log "  Deleting [iCloud] " & idx & "/" & moveTotal1
		move msg to trash1
		set movedCount to movedCount + 1
	end repeat

	-- Exchange Indbakke
	log "--- Processing Exchange Indbakke ---"
	set msgs2 to (messages of inbox2 whose deleted status is false)
	set total2 to count of msgs2
	log "Found " & total2 & " messages in Exchange Indbakke"
	set toMove2 to {}
	set idx to 0
	repeat with msg in msgs2
		set idx to idx + 1
		log "  Scanning [Exchange] " & idx & "/" & total2
		set sndr to sender of msg
		set matched to false
		repeat with target in targetSenders
			if sndr contains target then
				log "    -> Queuing: " & sndr & " | " & subject of msg
				set end of toMove2 to msg
				set matched to true
				exit repeat
			end if
		end repeat
		if not matched then
			set skippedCount to skippedCount + 1
		end if
	end repeat
	set moveTotal2 to count of toMove2
	log "Deleting " & moveTotal2 & " matched messages from Exchange Indbakke"
	set idx to 0
	repeat with msg in toMove2
		set idx to idx + 1
		log "  Deleting [Exchange] " & idx & "/" & moveTotal2
		move msg to trash2
		set movedCount to movedCount + 1
	end repeat
end tell

log "=== Cleanup Complete ==="
log "Moved:   " & movedCount & " emails"
log "Skipped: " & skippedCount & " emails"

return "Done. Moved " & movedCount & " emails to Deleted. Skipped " & skippedCount & "."
