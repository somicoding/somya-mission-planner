let userScore=0;
let compScore=0;
const choices=document.querySelectorAll(".choice");
const msg=document.querySelector("#msg");
const userscorep=document.querySelector("#user-score");
const compscorep=document.querySelector("#comp-score");

const generateCompC=()=>{
    const options=["rock","paper","scissors"];
    const randIdx=Math.floor(Math.random()*3);
    return options[randIdx];

}
const drawGame=()=>{
    console.log("game was draw");
    msg.innerText="Its a Draw!!";
    msg.style.backgroundColor="#081b31";
}
const showWin=(userWin,userChoice,compC)=>{
    if(userWin){
        userScore++;
        userscorep.innerText=userScore;
        console.log("You WIN!!");
        msg.innerText=`You Win! your ${userChoice} beats ${compC}`;
        msg.style.backgroundColor="green";
    }else{
        compScore++;
        compscorep.innerText=compScore;
        console.log("You LOSE!!");
        msg.innerText=`You Lose!${compC} beats your ${userChoice}`;
        msg.style.backgroundColor="red"; 
    }
    
}
let playGame=(userChoice)=>{
    console.log("user ki choice=",userChoice)
    // genrating...
    const compC=generateCompC();
    console.log("computer choice=",compC);
    if(userChoice===compC){
        // Draw hoga
        drawGame();
        
    }else{
        let userWin=true;
        if (userChoice==="rock"){
            // scissors,paper
            userWin=compC==="paper"?false:true;
        }else if(userChoice==="paper"){
            // rock,scissors
            userWin=compC==="scissors"?false:true;
        }else{
            // rock,paper
            userWin=compC==="rock"?false:true;
              
        }
        showWin(userWin,userChoice,compC);
    }
}
choices.forEach((choice)=>{
    console.log(choice);
    choice.addEventListener("click",()=>{
        const userChoice=choice.getAttribute("id")
        console.log("choice was clicked",userChoice);
        playGame(userChoice);

    });
})