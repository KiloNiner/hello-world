-- #!/usr/bin/osascript
-- cleanup_inbox.applescript
-- Moves newsletter/commercial emails from iCloud INBOX and Exchange Indbakke
-- to their respective Deleted folders.
-- Senders targeted: LinkedIn (3 addresses) + commercial newsletters/ads

set targetSenders to { ¬
	"messages-noreply@linkedin.com", ¬
	"jobalerts-noreply@linkedin.com", ¬
	"notifications-noreply@linkedin.com", ¬
	"newsletter@backerclub.co", ¬
	"hello@pen.store", ¬
	"nyhedsmail@email.ilva.com", ¬
	"kontakt@skousen.dk", ¬
	"news@news.toejeksperten.dk", ¬
	"newsletter@storybundle.com", ¬
	"dsb@mail.dsb.dk", ¬
	"familyclub@bones.dk", ¬
	"eu@news.ugreen.com", ¬
	"newsletter@update.just-eat.dk", ¬
	"marketing@proshop.dk", ¬
	"communications@stardockentertainment.info", ¬
	"info@newsletter.tipster.dk", ¬
	"elgiganten@email.elgiganten.dk", ¬
	"jonas@email.sunset-boulevard.dk", ¬
	"donotreply@audible.co.uk", ¬
	"app@hej.lagkagehuset.dk", ¬
	"contact@discoverscifi.com", ¬
	"followups@clean.email", ¬
	"mail@wagner.dk", ¬
	"news@news.wagner.dk", ¬
	"info.dk@sc.stenaline.com", ¬
	"monday.reply@brighttalk.com", ¬
	"noreply_at_glassdoor_com_zypwtjpq67_8a4c403d@privaterelay.appleid.com", ¬
	"fly_at_seaplanes_dk_ntk24arfj4504v_2b7x5967@icloud.com", ¬
	"mail@send.originaltalks.dk", ¬
	"media@fjordtours.dk", ¬
	"email.campaign@sg.booking.com", ¬
	"synology@news.synology.com", ¬
	"info@members.netflix.com", ¬
	"DoNotReply@ConnectedCommunity.org", ¬
	"sarahlindseycooke+killer-tater-tots@substack.com", ¬
	"aeg@marketing.aeg.com", ¬
	"notepad@theverge.com", ¬
	"kontakt@unsolved.se", ¬
	"subscriptions@theverge.com", ¬
	"groups-noreply@linkedin.com", ¬
	"noreply@bones.dk", ¬
	"hola@info.hotelsviva.com", ¬
	"DoNotReply@mcdonalds.com", ¬
	"prosa@info.prosa.dk", ¬
	"no-reply@order.just-eat.dk"}

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
