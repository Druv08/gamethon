// Protect the King - 2D. The protected objective.

#include "Characters/PTKKingCharacter.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/PTKHealthComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/CollisionProfile.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "PaperFlipbook.h"
#include "PaperFlipbookComponent.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKKingCharacter)

namespace PTKKingDefaults
{
	/**
	 * Same horizontal flip every other PTK character uses.
	 *
	 * The camera sits on the -Y side of the play plane, which is the only side
	 * Paper2D renders from here, and viewing from there mirrors the texture.
	 * This cancels it. See PTKCharacterDefaults in PTKTopDownCharacter.cpp -
	 * do not "fix" this by moving the camera; that makes sprites vanish.
	 */
	static constexpr float SpriteMirrorScaleX = -1.0f;

	/** The King is the objective: he outlasts a guard by a wide margin. */
	static constexpr float DefaultMaxHealth = 15000.0f;
}

APTKKingCharacter::APTKKingCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	// ---------------------------------------------------------------
	// Collision. Query-only on purpose.
	//
	// He is a landmark, not an obstacle: if he blocked movement, enemies
	// pathing past him would grind against a immovable capsule in the middle
	// of the arena. Overlap-only keeps him findable by the proximity scan and
	// by whatever targets him later, without ever pushing anything around.
	// ---------------------------------------------------------------
	Capsule = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Capsule"));
	if (Capsule)
	{
		Capsule->InitCapsuleSize(CollisionRadius, CollisionHalfHeight);
		Capsule->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Capsule->SetCollisionObjectType(ECC_Pawn);
		Capsule->SetCollisionResponseToAllChannels(ECR_Overlap);
		Capsule->SetGenerateOverlapEvents(true);
		SetRootComponent(Capsule);
	}

	// ---------------------------------------------------------------
	// Paper2D visual.
	// ---------------------------------------------------------------
	Sprite = CreateDefaultSubobject<UPaperFlipbookComponent>(TEXT("Sprite"));
	if (Sprite)
	{
		Sprite->SetupAttachment(Capsule);
		Sprite->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		Sprite->SetGenerateOverlapEvents(false);
		Sprite->PrimaryComponentTick.TickGroup = TG_PrePhysics;
		Sprite->SetRelativeRotation(FRotator::ZeroRotator);
		Sprite->SetRelativeLocation(FVector::ZeroVector);
		Sprite->SetRelativeScale3D(FVector(PTKKingDefaults::SpriteMirrorScaleX, 1.0f, 1.0f));
		Sprite->CastShadow = false;
		Sprite->bCastDynamicShadow = false;
		Sprite->bReceivesDecals = false;
		Sprite->SetLooping(true);
	}

	// ---------------------------------------------------------------
	// Health: the shared component, not a King-specific copy.
	// ---------------------------------------------------------------
	HealthComponent = CreateDefaultSubobject<UPTKHealthComponent>(TEXT("Health"));
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(PTKKingDefaults::DefaultMaxHealth);
	}

	Team = EPTKTeam::King;
}

void APTKKingCharacter::BeginPlay()
{
	Super::BeginPlay();

	AnchorLocation = GetActorLocation();

	if (HealthComponent)
	{
		HealthComponent->OnHealthChanged.AddDynamic(this, &APTKKingCharacter::HandleHealthChanged);
		HealthComponent->OnDeath.AddDynamic(this, &APTKKingCharacter::HandleDeath);
	}

	// The King never moves, so his depth offset is constant - computed once
	// here rather than re-applied every tick like the characters, who do move.
	if (Sprite && bEnableDepthSorting)
	{
		Sprite->SetRelativeLocation(
			FVector(0.0f, AnchorLocation.Z * DepthSortScale, 0.0f));
	}

	// Start from the true steady state rather than assuming Idle: the King may
	// well have been placed inside a spawner's ring.
	ScanForNearbyEnemies();
	State = EPTKKingState::Idle;
	EnterState(SteadyState());

	UE_LOG(LogPTK, Log,
		TEXT("%s ready: %.0f HP, alert radius %.0f, anchored at (%.0f, %.0f, %.0f)"),
		*GetName(),
		HealthComponent ? HealthComponent->GetMaxHealth() : 0.0f,
		AlertRadius, AnchorLocation.X, AnchorLocation.Y, AnchorLocation.Z);
}

void APTKKingCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// The King is stationary, full stop. Nothing in this class ever moves him,
	// but a stray physics impulse or a Blueprint nudge would, so the anchor is
	// re-asserted rather than trusted. This is the last line of defence behind
	// "he is an AActor, so nothing can possess or drive him".
	if (!GetActorLocation().Equals(AnchorLocation, 0.01f))
	{
		SetActorLocation(AnchorLocation, false, nullptr, ETeleportType::TeleportPhysics);
	}

	if (bLogHealthHeartbeat && HealthComponent)
	{
		HeartbeatTimer -= DeltaSeconds;
		if (HeartbeatTimer <= 0.0f)
		{
			HeartbeatTimer = HealthHeartbeatInterval;
			UE_LOG(LogPTK, Warning, TEXT("KING HEARTBEAT | t=%6.1f | HP %.1f/%.1f | state=%s"),
				GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f,
				HealthComponent->GetCurrentHealth(), HealthComponent->GetMaxHealth(),
				*UPTKTypesLibrary::KingStateToString(State));
		}
	}

	if (State == EPTKKingState::Dead)
	{
		return;
	}

	AlertScanTimer -= DeltaSeconds;
	if (AlertScanTimer <= 0.0f)
	{
		AlertScanTimer = AlertCheckInterval;
		ScanForNearbyEnemies();
	}

	if (StateTimeRemaining > 0.0f)
	{
		// A timed animation owns the King until it has played out. Proximity
		// changes are still tracked above, they just do not interrupt.
		StateTimeRemaining -= DeltaSeconds;
		if (StateTimeRemaining <= 0.0f)
		{
			StateTimeRemaining = 0.0f;
			EnterState(SteadyState());
		}
		return;
	}

	const EPTKKingState Desired = SteadyState();
	if (State != Desired)
	{
		EnterState(Desired);
	}

	if (bDrawAlertRadius)
	{
		// Drawn in the XZ play plane, not the engine's default XY, so the ring
		// reads as a circle on screen rather than as an edge-on line.
		DrawDebugCircle(GetWorld(), AnchorLocation, AlertRadius, 48,
			bEnemyNearby ? FColor::Red : FColor::Green, false, -1.0f, 0, 1.5f,
			FVector(1.0f, 0.0f, 0.0f), FVector(0.0f, 0.0f, 1.0f), false);
	}
}

EPTKKingState APTKKingCharacter::SteadyState() const
{
	return bEnemyNearby ? EPTKKingState::Alert : EPTKKingState::Idle;
}

UPaperFlipbook* APTKKingCharacter::FlipbookForState(EPTKKingState Query, float& OutRate) const
{
	switch (Query)
	{
	case EPTKKingState::Alert:
		OutRate = AlertPlayRate;
		return AlertFlipbook;
	case EPTKKingState::PowerCast:
		OutRate = PowerCastPlayRate;
		return PowerCastFlipbook;
	case EPTKKingState::Hit:
		OutRate = HitPlayRate;
		return ResolveHitFlipbook();
	case EPTKKingState::Dead:
		OutRate = DeathPlayRate;
		return DeathFlipbook;
	case EPTKKingState::Idle:
	default:
		OutRate = IdlePlayRate;
		return IdleFlipbook;
	}
}

UPaperFlipbook* APTKKingCharacter::ResolveHitFlipbook() const
{
	// No hit sheet was delivered for the King. Rather than invent one, the
	// alert reaction stands in: it is the closest thing in the supplied art to
	// "something just happened to him". Assign HitFlipbook and this vanishes.
	return HitFlipbook ? HitFlipbook.Get() : AlertFlipbook.Get();
}

void APTKKingCharacter::EnterState(EPTKKingState NewState)
{
	State = NewState;

	const bool bTimed = (NewState == EPTKKingState::PowerCast || NewState == EPTKKingState::Hit);
	const bool bOnce = bTimed || NewState == EPTKKingState::Dead;

	float Rate = 1.0f;
	UPaperFlipbook* const Book = FlipbookForState(NewState, Rate);
	Rate = FMath::Max(Rate, KINDA_SMALL_NUMBER);

	if (Sprite && Book)
	{
		Sprite->SetFlipbook(Book);
		Sprite->SetPlayRate(Rate);
		Sprite->SetLooping(!bOnce);
		Sprite->PlayFromStart();
	}

	if (bTimed)
	{
		// Hold the state for exactly one play-through, so the animation is
		// never cut off part-way and never lingers after it has finished.
		StateTimeRemaining = Book
			? Book->GetTotalDuration() / Rate
			: FallbackStateDuration;
	}
	else
	{
		StateTimeRemaining = 0.0f;
	}
}

void APTKKingCharacter::ScanForNearbyEnemies()
{
	bEnemyNearby = false;

	UWorld* const World = GetWorld();
	if (!World || AlertRadius <= 0.0f)
	{
		return;
	}

	FCollisionObjectQueryParams ObjectParams;
	ObjectParams.AddObjectTypesToQuery(ECC_Pawn);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKKingAlert), false, this);

	TArray<FOverlapResult> Overlaps;
	World->OverlapMultiByObjectType(Overlaps, AnchorLocation, FQuat::Identity,
		ObjectParams, FCollisionShape::MakeSphere(AlertRadius), Params);

	for (const FOverlapResult& Result : Overlaps)
	{
		const APTKEnemyCharacter* const Enemy = Cast<APTKEnemyCharacter>(Result.GetActor());
		// A corpse is not a threat: dead enemies must not hold him in Alert.
		if (Enemy && !Enemy->IsDead())
		{
			bEnemyNearby = true;
			return;
		}
	}
}

bool APTKKingCharacter::TriggerPowerCast()
{
	if (State == EPTKKingState::Dead)
	{
		return false;
	}

	// Already casting: refuse rather than restart. Re-entering every frame
	// would keep resetting the flipbook to frame 1 and it would never visibly
	// play - the classic "my animation is stuck on its first frame" bug.
	if (State == EPTKKingState::PowerCast)
	{
		return false;
	}

	EnterState(EPTKKingState::PowerCast);
	UE_LOG(LogPTK, Log, TEXT("%s power cast (%.2fs) - animation only, no buff applied yet"),
		*GetName(), StateTimeRemaining);
	return true;
}

void APTKKingCharacter::DebugApplyDamage(float Amount)
{
	if (HealthComponent && Amount > 0.0f)
	{
		HealthComponent->ApplyDamage(Amount, this);
	}
}

void APTKKingCharacter::DebugSetAlertRadius(float NewRadius)
{
	AlertRadius = FMath::Max(0.0f, NewRadius);
	// Re-scan at once so the change is visible on this frame rather than
	// whenever the next scheduled scan happens to land.
	ScanForNearbyEnemies();
	AlertScanTimer = AlertCheckInterval;
	if (State != EPTKKingState::Dead && StateTimeRemaining <= 0.0f)
	{
		const EPTKKingState Desired = SteadyState();
		if (State != Desired)
		{
			EnterState(Desired);
		}
	}
}

void APTKKingCharacter::HandleHealthChanged(UPTKHealthComponent* /*Component*/,
	float NewHealth, float Delta, AActor* DamageInstigator)
{
	// Healing and the initial fill are not hit reactions.
	if (Delta >= 0.0f || State == EPTKKingState::Dead)
	{
		return;
	}

	// Deliberately Warning, and deliberately only on an actual damage event -
	// never per tick. The King should be untouched unless something really
	// hit him, so any line at all here is worth reading, and it carries enough
	// provenance to identify the culprit without a debugger.
	UE_LOG(LogPTK, Warning,
		TEXT("KING DAMAGE | Amount: %.1f | HP before: %.1f | HP after: %.1f | ")
		TEXT("Causer: %s | Instigator: %s | Source: %hs | Time: %.2f"),
		-Delta,
		NewHealth - Delta,
		NewHealth,
		*GetNameSafe(DamageInstigator),
		DamageInstigator ? *GetNameSafe(DamageInstigator->GetInstigator()) : TEXT("none"),
		__FUNCTION__,
		GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f);

	// The death broadcast follows this one, and it wins: starting a hit
	// reaction here would immediately be overwritten by the collapse.
	if (NewHealth <= 0.0f)
	{
		return;
	}

	// Let a reaction finish before starting another. Without this, sustained
	// damage restarts the flipbook every frame and the King twitches on frame
	// 1 forever instead of playing a reaction - which is exactly the "repeated
	// damage corrupts the animation state" failure.
	if (State == EPTKKingState::Hit && StateTimeRemaining > 0.0f)
	{
		return;
	}

	EnterState(EPTKKingState::Hit);
}

void APTKKingCharacter::HandleDeath(UPTKHealthComponent* /*Component*/, AActor* Killer)
{
	if (State == EPTKKingState::Dead)
	{
		return;
	}

	EnterState(EPTKKingState::Dead);
	StateTimeRemaining = 0.0f;

	// No more alert scans, no more casts, no more hit reactions: Tick returns
	// immediately once Dead, and every entry point above checks for it.

	// Overlap off so nothing can keep targeting or reacting to the body, but
	// the actor itself is NOT destroyed and gets no lifespan. The King is the
	// objective - his defeated body has to stay on screen.
	if (Capsule)
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	const float Length = (Sprite && Sprite->GetFlipbook())
		? Sprite->GetFlipbook()->GetTotalDuration() / FMath::Max(DeathPlayRate, KINDA_SMALL_NUMBER)
		: 0.0f;

	UE_LOG(LogPTK, Warning, TEXT("KING DEFEATED - %s killed by %s (collapse %.2fs, body remains)"),
		*GetName(), Killer ? *Killer->GetName() : TEXT("unknown"), Length);
}
