hmm

for devin: 
- i'd like to migrate to postgresql. i wonder if there's anything we did because we're using sqlite that we could do differently and simpler with postgresql. that means the db will be in the docker compose

i guess let me propose a broader change: 
- onboarding is a tab on the sidebar.
- as part of onboarding, i'd like to allow the user to upload pdfs 
- there should be some documents table? 
- the onboarding table is currently useful for keeping the proposed but not accepted filters. i think we should just make "draft" a column in the filters table