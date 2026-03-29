box::use(
  shiny,
  bslib,
)

box::use(
  app/view/about,
  app/view/analyze,
)

#' @export
ui <- function(id) {
  ns <- shiny$NS(id)
  shiny$tagList(
    # Main content area wrapped in a container
    shiny$tags$div(
      style = "min-height: calc(100vh - 100px); padding-bottom: 100px;", # Adjust for footer height
      bslib$page_navbar(
        position = "fixed-top",
        id = ns("tabs"),

        # Title with custom logo and text
        title = shiny$tags$div(
          style = "display: inline-flex; align-items: center;",  # Inline-flex for proper inline behavior
          shiny$img(src = "static/favicon.ico",
          style = "float:left; margin-right:0.8rem; width:1.6rem;"),
          "Municipal Sales Tax Analysis Tool"
        ),
        
        # Navigation Panels
        bslib$nav_panel(title = "About",
        shiny$br(), 
          about$ui(ns("about"))
        ),
        bslib$nav_panel(title = "Analysis Tool",
        shiny$br(), shiny$br(),
          analyze$ui(ns("analyze"))
        )
      )
    ),
    
    # Footer with custom content and disclaimer
    shiny$tags$footer(
      style = "position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f8f9fa; padding: 15px 20px; text-align: center; font-size: 0.9rem; box-shadow: 0 -2px 5px rgba(0, 0, 0, 0.1);",
      
   
      
      shiny$tags$div(
        style = "font-size: 0.8rem; color: #666; margin-top: 10px; line-height: 1.4;",
        "Disclaimer: This tool is provided as a resource to assist municipalities in analyzing sales tax revenue data. The City of Yukon, Mayor Brian Pillmore, and all associated parties disclaim any liability for decisions made based on the forecasts or data presented by this tool. Users are advised to consult with financial professionals before making any significant fiscal decisions."
      )
    )
  )
}

#' @export
server <- function(id) {
  shiny$moduleServer(id, function(input, output, session) {
    about$server("about")
    analyze$server("analyze")
  })
}
