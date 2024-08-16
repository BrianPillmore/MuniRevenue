box::use(
  shiny,
  shinyjs,
)

box::use(
  app/view/homepage,
)
#' @export
ui <- function(id) {
  ns <- shiny$NS(id)
  shiny$tagList(
    shinyjs$useShinyjs(),  # Initialize shinyjs
    homepage$ui(ns("homepage"))
   
  )
}

#' @export
server <- function(id) {
  shiny$moduleServer(id, function(input, output, session) {
    homepage$server("homepage")
   

  })
}
