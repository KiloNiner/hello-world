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
	set msgs1 to messages of inbox1
	log "Found " & (count of msgs1) & " messages in iCloud INBOX"
	repeat with msg in msgs1
		set sndr to sender of msg
		set matched to false
		repeat with target in targetSenders
			if sndr contains target then
				log "  MOVING [iCloud]: " & sndr & " | " & subject of msg
				move msg to trash1
				set movedCount to movedCount + 1
				set matched to true
				exit repeat
			end if
		end repeat
		if not matched then
			set skippedCount to skippedCount + 1
		end if
	end repeat

	-- Exchange Indbakke
	log "--- Processing Exchange Indbakke ---"
	set msgs2 to messages of inbox2
	log "Found " & (count of msgs2) & " messages in Exchange Indbakke"
	repeat with msg in msgs2
		set sndr to sender of msg
		set matched to false
		repeat with target in targetSenders
			if sndr contains target then
				log "  MOVING [Exchange]: " & sndr & " | " & subject of msg
				move msg to trash2
				set movedCount to movedCount + 1
				set matched to true
				exit repeat
			end if
		end repeat
		if not matched then
			set skippedCount to skippedCount + 1
		end if
	end repeat
end tell

log "=== Cleanup Complete ==="
log "Moved:   " & movedCount & " emails"
log "Skipped: " & skippedCount & " emails"

return "Done. Moved " & movedCount & " emails to Deleted. Skipped " & skippedCount & "."
