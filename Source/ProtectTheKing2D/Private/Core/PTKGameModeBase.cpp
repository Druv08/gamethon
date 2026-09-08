// Protect the King - 2D. Base game mode.

#include "Core/PTKGameModeBase.h"
#include "Core/PTKEnemySpawner.h"
#include "Core/PTKWaveManager.h"
#include "Engine/World.h"
#include "EngineUtils.h"

#include "Core/PTKCombatHUD.h"
#include "Core/PTKPlayerController.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "ProtectTheKing2D.h"
#include "UObject/ConstructorHelpers.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGameModeBase)

APTKGameModeBase::APTKGameModeBase()
{
	// Prototype combat readout: health bars and the AI state block. Pure canvas
	// drawing, no widget assets - see APTKCombatHUD. Replaced by the real
	// interface later.
	HUDClass = APTKCombatHUD::StaticClass();

	// Guard switching lives on the controller, not on the pawn, so that the
	// number keys survive the pawn being swapped out from under them. See
	// APTKPlayerController.
	PlayerControllerClass = APTKPlayerController::StaticClass();

	// Ravager is slot 1, and the guard the player starts on. The other four are
	// placed in the level and are AI-driven until a number key says otherwise;
	// this is only the starting point, not the only guard the player gets.
	static ConstructorHelpers::FClassFinder<APawn> RavagerBP(
		TEXT("/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"));

	if (RavagerBP.Succeeded())
	{
		DefaultPawnClass = RavagerBP.Class;
	}
	else
	{
		// Expected on a fresh clone before the Blueprint has been generated.
		UE_LOG(LogPTK, Warning,
			TEXT("BP_Ravager was not found at /Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager. ")
			TEXT("Run Tools/PTK_GenerateAssets.py, then set DefaultPawnClass."));
	}
}

bool APTKGameModeBase::IsGameplayActive(const UWorld* World)
{
	const APTKGameModeBase* Mode = World ? World->GetAuthGameMode<APTKGameModeBase>() : nullptr;

	// A finished run is not active play. Testing the result here rather than at
	// each caller is what makes the victory and defeat screens freeze combat,
	// input, spawning and guard switching all at once - every one of those
	// already asks this question before it does anything.
	return Mode && Mode->IsPlaying() && !Mode->IsMatchOver();
}

void APTKGameModeBase::StartGame()
{
	if (bPlaying) return;
	bPlaying = true;
	for (TActorIterator<APTKPlayerController> It(GetWorld()); It; ++It)
	{
		It->HideStartScreen();
	}

	// The wave manager is the real spawning system. APTKEnemySpawner is kept as
	// a stress-test tool and only wakes if one was deliberately left in the
	// level with spawning enabled.
	if (APTKWaveManager* Waves = APTKWaveManager::Get(GetWorld()))
	{
		Waves->StartRun();
	}
	else
	{
		for (TActorIterator<APTKEnemySpawner> It(GetWorld()); It; ++It)
		{
			It->StartSpawning();
		}
	}
	UE_LOG(LogPTK, Log, TEXT("GAME START | Playing"));
}

void APTKGameModeBase::NotifyKingDefeated()
{
	EndRun(EPTKMatchResult::Defeat);
}

void APTKGameModeBase::NotifyWavesCleared()
{
	EndRun(EPTKMatchResult::Victory);
}

void APTKGameModeBase::EndRun(EPTKMatchResult Result)
{
	if (MatchResult != EPTKMatchResult::InProgress)
	{
		return;
	}
	MatchResult = Result;

	if (APTKWaveManager* Waves = APTKWaveManager::Get(GetWorld()))
	{
		Waves->StopRun();
	}
	for (TActorIterator<APTKEnemySpawner> It(GetWorld()); It; ++It)
	{
		It->ClearWave();
	}

	UE_LOG(LogPTK, Warning, TEXT("MATCH OVER | %s"),
		Result == EPTKMatchResult::Victory ? TEXT("VICTORY - the King survived")
		: TEXT("DEFEAT - the King has fallen"));
}

// ---------------------------------------------------------------------------
// Ending a run and starting another
// ---------------------------------------------------------------------------

namespace
{
	/**
	 * Seed handed from a Restart to the run it starts. Zero means "randomise".
	 *
	 * File-static because it has to outlive the level reload that carries it:
	 * every actor and object in the world, this game mode included, is
	 * destroyed and rebuilt in between.
	 */
	int32 GPendingWaveSeed = 0;
}

int32 APTKGameModeBase::ConsumePendingWaveSeed()
{
	const int32 Seed = GPendingWaveSeed;
	GPendingWaveSeed = 0;
	return Seed;
}

void APTKGameModeBase::RestartRun()
{
	// Carry this run's seed over so the next one deals the same corners, lanes
	// and wave composition. Zero if there is no wave manager to ask, which
	// simply degrades to a fresh run.
	GPendingWaveSeed = 0;
	for (TActorIterator<APTKWaveManager> It(GetWorld()); It; ++It)
	{
		GPendingWaveSeed = It->GetActiveSeed();
		break;
	}

	UE_LOG(LogPTK, Warning, TEXT("FLOW | RESTART | replaying seed %d"), GPendingWaveSeed);
	ReloadLevel();
}

void APTKGameModeBase::NewGameRun()
{
	GPendingWaveSeed = 0;
	UE_LOG(LogPTK, Warning, TEXT("FLOW | NEW GAME | fresh randomisation"));
	ReloadLevel();
}

void APTKGameModeBase::ReloadLevel()
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	// The reloaded level comes up in WaitingToStart, exactly as a cold launch
	// does, so the player meets the start screen again rather than walking into
	// a fight already in progress.
	const FName Current(*UGameplayStatics::GetCurrentLevelName(World, true));
	UGameplayStatics::OpenLevel(World, Current);
}
