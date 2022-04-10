:PROPERTIES:
:END:
(put 'narrow-to-region 'disabled nil)


(defun knock/insert-ticket ()
  (interactive)
  (setq ticket (read-string "Ticket? "))
  (if (string-empty-p ticket)
      nil
    (progn
      (org-insert-property-drawer)
      (org-entry-put-multivalued-property
       nil
       "TICKET"
       ticket
       (concat "https://knockr.atlassian.net/browse/" ticket)))))

(defun set-slack-status (emoji status)
 (with-temp-buffer
   (call-process-shell-command
    (concat
     "/home/jack/Code/go/slack/slack -token /home/jack/Code/go/slack/.token -cookie /home/jack/Code/go/slack/.cookie "
     "-s '" status "' "
     "-e '" emoji "'"
     " >> /tmp/slack.log")
    nil
    0)))

(defun knock/set-slack-status ()
  (interactive)
  (setq ticket (org-entry-get-multivalued-property nil "TICKET"))
  (setq slackStatus (org-entry-get-multivalued-property nil "STATUS"))
  (setq org-jira-id (org-entry-get-multivalued-property nil "ID"))
  (when (and (not ticket) org-jira-id)
      (setq ticket org-jira-id)
      (setq slackStatus (list ":computer:")))

  (setq emoji (if (> (length slackStatus) 0)
                   (car slackStatus)
                 ":computer:")
        statusLine (if (> (length ticket) 0)
                        (concat "Working on " (car ticket))
                      (if (> (length slackStatus) 0)
                          (string-join (cdr slackStatus) " ")
                        "")))

  (set-slack-status emoji statusLine))

(defun knock/clear-slack-status ()
  (interactive)
  (set-slack-status "" ""))

(defun knock/set-slack-clear () (knock/clear-slack-status))


;; This function was found on a stackoverflow post -> https://stackoverflow.com/questions/6681407/org-mode-capture-with-sexp
(defun get-page-title (url)
  "Get title of web page, whose url can be found in the current line"
  ;; Get title of web page, with the help of functions in url.el
  (with-current-buffer (url-retrieve-synchronously url)
    ;; find title by grep the html code
    (goto-char 0)
    (re-search-forward "<title>\\([^<]*\\)</title>" nil t 1)
    (setq web_title_str (match-string 1))
    ;; find charset by grep the html code
    (goto-char 0)

    ;; find the charset, assume utf-8 otherwise
    (if (re-search-forward "charset=\\([-0-9a-zA-Z]*\\)" nil t 1)
        (setq coding_charset (downcase (match-string 1)))
      (setq coding_charset "utf-8")
      ;; decode the string of title.
      (setq web_title_str (decode-coding-string web_title_str (intern
                                                               coding_charset))))
    (concat "[[" url "][" web_title_str "]]")))


(add-hook 'org-mode-hook
          (lambda ()
            (defadvice org-clock-out
              (after org-clock-out-after activate)
              (knock/clear-slack-status))
            (defadvice org-clock-in
              (after org-clock-in-after activate)
              (knock/set-slack-status))))

(custom-set-variables
 ;; custom-set-variables was added by Custom.
 ;; If you edit it by hand, you could mess it up, so be careful.
 ;; Your init file should contain only one such instance.
 ;; If there is more than one, they won't work right.
 '(custom-safe-themes
   '("be9645aaa8c11f76a10bcf36aaf83f54f4587ced1b9b679b55639c87404e2499" default))
 '(org-agenda-files
   '("~/org/appts.org" "~/org/clocktable.org" "~/org/notes.org" "~/org/tickler.org" "~/org/todo.org" "~/.cache/org-jira/.org" "~/.cache/org-jira/CRM.org" "~/.cache/org-jira/DB.org" "~/.cache/org-jira/boards-list.org" "~/.cache/org-jira/projects-list.org"))
 '(org-jira-jira-status-to-org-keyword-alist
   '(("To Do" . "TODO")
     ("Code Review" . "WAIT")
     ("In Progress" . "STRT")
     ("Validating" . "NEXT")
     ("Awaiting Deployment" . "WAIT")
     ("Stage" . "WAIT")
     ("Engineering Work Complete" . "DONE")))
 '(org-jira-working-dir "~/.cache/org-jira" t)
 '(package-selected-packages '(org org-jira org-alert))
 '(safe-local-variable-values '((org-clock-into-drawer . CLOCK)))
 '(send-mail-function 'smtpmail-send-it)
 '(smtpmail-smtp-server "smtp.gmail.com")
 '(smtpmail-smtp-service 587))
(custom-set-faces
 ;; custom-set-faces was added by Custom.
 ;; If you edit it by hand, you could mess it up, so be careful.
 ;; Your init file should contain only one such instance.
 ;; If there is more than one, they won't work right.
 )
